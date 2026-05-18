import json
import re
from functools import lru_cache

from django.conf import settings
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import logout as django_logout
from django.contrib.auth import SESSION_KEY as DJANGO_AUTH_USER_ID
from django.contrib.auth import BACKEND_SESSION_KEY as DJANGO_AUTH_BACKEND
from django.contrib.auth import HASH_SESSION_KEY as DJANGO_AUTH_HASH

from techno_chat.settings import logger

from .models import User, UserProfile, File, ChatSession, ChatMessage
from .forms import FileUploadForm
from .helpers import (
    attach_user_file_display_ids,
    detect_file_type, normalize_file_type, _get_user, _get_or_create_profile, _nav_context,
    is_network_error, is_quota_error
)
from .conversation_state_service import (
    answer_conversation_focus_query,
    answer_personal_memory_query,
    extract_personal_memory_update,
    get_conversation_state,
    get_last_active_chat_session_id,
    set_last_active_chat_session,
    update_conversation_state,
)
from .page_render_service import get_page_render, get_source_content, get_source_fallback_content, get_visual_render
from .document_reader import docx_file_text
from .ai_assistant_service import build_ai_assistant_prompt
from .web_search_service import build_web_search_prompt
from .ingestion_service import embed_file_and_upsert
from .chat_service import build_chat_prompt
from .image_generation_service import build_image_generation_prompt
from .validators import (
    validate_uploaded_files_length,
    validate_uploaded_file_type,
    validate_file_size,
    validate_profile_username,
    validate_login_credentials,
    validate_profile_fields,
    validate_chat_query,
    validate_session_has_files,
    validate_chat_mode,
    validate_session_type,
)
from .choices import FileProcessingStatus, ContributorTeamChoices
from .exceptions import (
    TechnoChatError, NetworkConnectionError, ChatResponseError,
    ChatModelQuotaError, ChatMessageSendError
)
from .constants import (
    CHAT_HISTORY_COUNT,
    CHAT_MODE_RAG, CHAT_MODE_AI_ASSISTANT, CHAT_MODE_WEB_SEARCH,
    SESSION_TYPE_FILE, SESSION_TYPE_GENERAL,
    PAGE_RENDER_SUPPORTED_TYPES, CHAT_MODE_IMAGE_GENERATION,
)


# =============================================================================
# AUTH VIEWS
# =============================================================================

_SESSION_RESET_KEYS = ("user_id", "conversation_state", "last_chat_session_id")


def _clear_user_session_state(request):
    for key in _SESSION_RESET_KEYS:
        request.session.pop(key, None)
    request.session.modified = True


def _clear_admin_session_state(request):
    for key in ("tc_admin_id", "role", DJANGO_AUTH_USER_ID, DJANGO_AUTH_BACKEND, DJANGO_AUTH_HASH):
        request.session.pop(key, None)
    request.session.modified = True


def _ordered_range(start, end):
    if start is None:
        return None, None
    if end is None:
        return start, start
    return (start, end) if start <= end else (end, start)


def _format_chat_source_ref(source: dict) -> str:
    file_type = normalize_file_type(source.get("file_type") or "", source.get("file_name") or "")
    if file_type == "md" and source.get("section_name"):
        start, end = _ordered_range(source.get("line_start"), source.get("line_end"))
        if start is not None and end is not None and start != end:
            return f"§ {source['section_name']} · Lines {start}–{end}"
        if start is not None:
            return f"§ {source['section_name']} · Line {start}"
        return f"§ {source['section_name']}"
    if file_type in {"ppt", "pptx"} and source.get("slide_index") is not None:
        return f"Slide {source['slide_index']}"
    if file_type in {"xlsx", "xls"} and source.get("row_start") is not None:
        start, end = _ordered_range(source.get("row_start"), source.get("row_end"))
        prefix = f"{source['sheet_name']} · " if source.get("sheet_name") else ""
        if start is not None and end is not None and start != end:
            return f"{prefix}Rows {start}–{end}"
        return f"{prefix}Row {start}"
    if file_type == "csv" and source.get("row_start") is not None:
        start, end = _ordered_range(source.get("row_start"), source.get("row_end"))
        if start is not None and end is not None and start != end:
            return f"Rows {start}–{end}"
        return f"Row {start}"
    if file_type == "txt" and source.get("line_start") is not None:
        start, end = _ordered_range(source.get("line_start"), source.get("line_end"))
        if start is not None and end is not None and start != end:
            return f"Lines {start}–{end}"
        return f"Line {start}"
    if source.get("page_index") is not None:
        start, end = _ordered_range(source.get("page_index"), source.get("page_end"))
        if start is not None and end is not None and start != end:
            return f"Pages {start}–{end}"
        return f"Page {start}"
    return ""


@lru_cache(maxsize=128)
def _docx_page_count_for_file(file_id: int, updated_at_key: str) -> int | None:
    try:
        file_obj = File.objects.get(id=file_id)
        segments = docx_file_text(file_obj.file.path)
    except Exception:
        return None

    page_numbers = [item.get("page_index") for item in segments if item.get("page_index") is not None]
    if not page_numbers:
        return 1
    return max(page_numbers)


def _normalize_docx_source(source: dict) -> dict:
    normalized = dict(source)
    file_type = normalize_file_type(source.get("file_type") or "", source.get("file_name") or "")
    if file_type not in {"doc", "docx"}:
        return normalized

    file_id = source.get("file_id")
    if not file_id:
        return normalized

    try:
        file_obj = File.objects.only("id", "updated_at").get(id=file_id)
    except File.DoesNotExist:
        return normalized

    page_count = _docx_page_count_for_file(file_obj.id, file_obj.updated_at.isoformat())
    if not page_count:
        return normalized

    page_index = normalized.get("page_index")
    if page_index is not None:
        normalized["page_index"] = max(1, min(page_index, page_count))

    page_end = normalized.get("page_end")
    if page_end is not None:
        clamped_end = max(1, min(page_end, page_count))
        if normalized.get("page_index") is not None:
            clamped_end = max(normalized["page_index"], clamped_end)
        normalized["page_end"] = clamped_end

    return normalized


def _normalize_chat_sources(sources, chat_mode: str):
    if chat_mode != CHAT_MODE_RAG:
        return list(sources or [])
    normalized_sources = []
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        normalized_sources.append(_normalize_docx_source(src))
    return normalized_sources


def _prepare_sources_for_display(sources, chat_mode: str):
    prepared = []
    for src in _normalize_chat_sources(sources, chat_mode):
        if not isinstance(src, dict):
            continue
        if src.get("kind") in {"generated_image", "uploaded_image"}:
            continue
        if chat_mode == CHAT_MODE_AI_ASSISTANT:
            continue
        if chat_mode == CHAT_MODE_WEB_SEARCH:
            prepared.append(src)
            continue
        if chat_mode != CHAT_MODE_RAG:
            continue
        normalized_file_type = normalize_file_type(src.get("file_type") or "", src.get("file_name") or "")
        prepared.append(
            {
                **src,
                "file_type": normalized_file_type,
                "display_ref": _format_chat_source_ref(src),
                "display_file_name": src.get("file_name", ""),
                "display_label": f"{src.get('file_name', '')} · {_format_chat_source_ref(src)}".strip(" ·"),
                "is_previewable": normalized_file_type not in {"csv", "xlsx", "xls", "excel"},
                "page_range_start": _ordered_range(src.get("page_index"), src.get("page_end"))[0],
                "page_range_end": _ordered_range(src.get("page_index"), src.get("page_end"))[1],
                "line_range_start": _ordered_range(src.get("line_start"), src.get("line_end"))[0],
                "line_range_end": _ordered_range(src.get("line_start"), src.get("line_end"))[1],
                "row_range_start": _ordered_range(src.get("row_start"), src.get("row_end"))[0],
                "row_range_end": _ordered_range(src.get("row_start"), src.get("row_end"))[1],
            }
        )
    return prepared


def _detect_chat_intent(query: str, requested_chat_mode: str, uploaded_image, conversation_state: dict | None) -> str:
    lowered = (query or "").strip().lower()
    if uploaded_image or requested_chat_mode == CHAT_MODE_IMAGE_GENERATION:
        return CHAT_MODE_IMAGE_GENERATION
    if extract_personal_memory_update(query):
        return "personal_memory_store"
    if answer_personal_memory_query(query, conversation_state):
        return "personal_memory_recall"
    if answer_conversation_focus_query(query, conversation_state):
        return "conversation_focus_recall"
    if lowered in {"hi", "hello", "hey", "good morning", "good evening", "good afternoon"}:
        return "greeting"
    if requested_chat_mode == CHAT_MODE_WEB_SEARCH:
        return CHAT_MODE_WEB_SEARCH
    if requested_chat_mode == CHAT_MODE_AI_ASSISTANT:
        return CHAT_MODE_AI_ASSISTANT
    return CHAT_MODE_RAG

def login_view(request):
    error = None
    if request.method == "POST":
        email = request.POST.get("email", " ").strip()
        password = request.POST.get("password", " ")

        try:
            validate_login_credentials(email, password)
            user = User.objects.filter(email=email, password=password).first()
            if user:
                request.session["user_id"] = user.id
                profile = _get_or_create_profile(user)
                if not profile.is_profile_complete:
                    return redirect("profile")
                return redirect("home")
            else:
                error = "Invalid email or password."
        except TechnoChatError as e:
            error = e.user_message

    return render(request, "login.html", {"error": error})


def logout_view(request):
    _clear_user_session_state(request)
    return redirect("login")


def admin_logout_view(request):
    django_logout(request)
    return redirect("admin:login")


# =============================================================================
# FILE VIEWS
# =============================================================================

def file_list_view(request):
    user = _get_user(request)
    if not user:
        return redirect("login")

    files = File.objects.filter(user=user).order_by("-created_at")
    files = attach_user_file_display_ids(files)
    context = {
        "user": user,
        "files": files,
        **_nav_context(user),
    }
    return render(request, "upload.html", context)


def upload_file_view(request):
    user = _get_user(request)
    if not user:
        return redirect("login")

    error = None
    success = False

    if request.method == "POST":
        try:
            files = request.FILES.getlist("file")
            validate_uploaded_files_length(files)

            uploaded_file = files[0]
            file_type = detect_file_type(uploaded_file.name)
            validate_uploaded_file_type(file_type)
            validate_file_size(uploaded_file, file_type)

            data = request.POST.copy()
            data["user"] = user.id
            data["file_type"] = file_type

            form = FileUploadForm(data, request.FILES)
            if form.is_valid():
                file_object = form.save(commit=False)
                file_object.original_filename = uploaded_file.name
                file_object.save()

                # Run ingestion pipeline
                embed_file_and_upsert(file_object)

                success = True
            else:
                error = str(form.errors)

        except TechnoChatError as e:
            error = e.user_message
        except Exception as e:
            logger.error("upload_file_view | exception: %s", e)
            error = "An unexpected error occurred during file upload."

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": success, "error": error})
    return redirect("file_list")


# =============================================================================
# CHAT SESSION VIEWS
# =============================================================================

def create_session_view(request):
    user = _get_user(request)
    if not user:
        return redirect("login")

    if request.method == "POST":
        title = request.POST.get("title", "").strip() or "New Chat"
        file_ids = request.POST.getlist("file_ids")

        # Read and validate session_type — safe fallback to chat_with_file
        session_type = request.POST.get("session_type", SESSION_TYPE_FILE).strip()
        try:
            validate_session_type(session_type)
        except TechnoChatError:
            session_type = SESSION_TYPE_FILE

        # Create the session with session_type
        session = ChatSession.objects.create(
            user=user,
            title=title,
            session_type=session_type,
        )

        # Only link files when session type is chat_with_file and files were selected
        if session_type == SESSION_TYPE_FILE and file_ids:
            completed_files = File.objects.filter(
                id__in=file_ids,
                user=user,
                embedding_status=FileProcessingStatus.COMPLETED,
            )
            session.files.set(completed_files)

        return redirect("chat", session_id=session.id)

    # GET: show file selection form
    completed_files = File.objects.filter(
        user=user,
        embedding_status=FileProcessingStatus.COMPLETED,
    )
    context = {
        "user": user,
        "files": completed_files,
        **_nav_context(user),
    }
    return render(request, "create_session.html", context)


def chat_view(request, session_id):
    user = _get_user(request)
    if not user:
        return redirect("login")

    session = get_object_or_404(ChatSession, id=session_id, user=user)
    set_last_active_chat_session(request, session.id)
    sessions = (
        ChatSession.objects
        .filter(user=user)
        .annotate(message_count=Count("messages"))
        .order_by("-created_at")
    )
    messages = ChatMessage.objects.filter(session=session).order_by("created_at")
    for message in messages:
        message.display_sources = _prepare_sources_for_display(message.sources, getattr(message, "chat_mode", ""))

    # Available models
    all_models = list(settings.GEMINI_LLM_MODELS.keys()) + list(settings.GROQ_LLM_MODELS.keys())

    context = {
        "user": user,
        "session": session,
        "session_type": session.session_type,   # NEW — tells template which buttons to show
        "sessions": sessions,
        "messages": messages,
        "models": all_models,
        "session_files": session.files.all(),
        **_nav_context(user),
    }
    return render(request, "chat.html", context)


def chat_list_view(request):
    """Redirect to the last active chat or to the most recent chat."""
    user = _get_user(request)
    if not user:
        return redirect("login")

    last_active_id = get_last_active_chat_session_id(request)
    if last_active_id:
        active_session = ChatSession.objects.filter(user=user, id=last_active_id).first()
        if active_session:
            return redirect("chat", session_id=active_session.id)

    latest = ChatSession.objects.filter(user=user).order_by("-created_at").first()
    if latest:
        return redirect("chat", session_id=latest.id)
    return redirect("create_session")


def chat_send_view(request, session_id):
    """API endpoint: POST query + model_name + chat_mode → route → LLM → save → return JSON."""
    user = _get_user(request)
    if not user:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    session = get_object_or_404(ChatSession, id=session_id, user=user)

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        body = request.POST
    else:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            body = request.POST

    query      = body.get("query", "").strip()
    model_name = body.get("model_name", "")
    chat_mode  = body.get("chat_mode", CHAT_MODE_RAG).strip().lower()
    uploaded_image = request.FILES.get("image")

    try:
        # ── 1. Validate query and chat mode ──────────────────────────────────
        validate_chat_query(query)
        validate_chat_mode(chat_mode)

        if not model_name:
            model_name = list(settings.GEMINI_LLM_MODELS.keys())[0]

        # ── 2. Get file_ids linked to this session ───────────────────────────
        file_ids = list(session.files.values_list("id", flat=True))
        strict_document_context = session.session_type == SESSION_TYPE_FILE

        # Only require files for RAG mode — AI Assistant and Web Search need none
        if uploaded_image and chat_mode != CHAT_MODE_IMAGE_GENERATION:
            raise ChatResponseError("Select Create Image mode to upload an image.")
        if chat_mode == CHAT_MODE_RAG:
            validate_session_has_files(file_ids)

        # ── 3. Get chat history (oldest first) ───────────────────────────────
        chat_history = list(
            ChatMessage.objects.filter(session=session)
            .order_by("-created_at")[:CHAT_HISTORY_COUNT]
        )
        chat_history.reverse()
        conversation_state = get_conversation_state(request, session.id)
        detected_intent = _detect_chat_intent(query, chat_mode, uploaded_image, conversation_state)

        if detected_intent == "personal_memory_store":
            update_conversation_state(request, session.id, query=query, resolved_query=query)
            set_last_active_chat_session(request, session.id)
            prompt = f"I'll remember that your name is {extract_personal_memory_update(query)['name']}."
            sources = []
            is_greeting = False
            is_summary = False
            effective_chat_mode = CHAT_MODE_AI_ASSISTANT
            image_urls = []
            resolved_query = query
            selected_model = model_name or list(settings.GEMINI_LLM_MODELS.keys())[0]
        elif detected_intent == "personal_memory_recall":
            remembered_name = answer_personal_memory_query(query, conversation_state)
            prompt = remembered_name or "I don't know your name yet."
            sources = []
            is_greeting = False
            is_summary = False
            effective_chat_mode = CHAT_MODE_AI_ASSISTANT
            image_urls = []
            resolved_query = query
            selected_model = model_name or list(settings.GEMINI_LLM_MODELS.keys())[0]
            update_conversation_state(request, session.id, query=query, resolved_query=query)
            set_last_active_chat_session(request, session.id)
        elif detected_intent == "conversation_focus_recall":
            focus_answer = answer_conversation_focus_query(query, conversation_state, has_document=bool(file_ids))
            prompt = focus_answer or "We have not set a clear topic yet."
            sources = []
            is_greeting = False
            is_summary = False
            effective_chat_mode = chat_mode
            image_urls = []
            resolved_query = query
            selected_model = model_name or list(settings.GEMINI_LLM_MODELS.keys())[0]
            update_conversation_state(request, session.id, query=query, resolved_query=query)
            set_last_active_chat_session(request, session.id)
        else:

            # ── 4. Route to the correct service ─────────────────────────────────

            try:
                if detected_intent == CHAT_MODE_IMAGE_GENERATION:
                    result = build_image_generation_prompt(
                        query=query,
                        request=request,
                        uploaded_image=uploaded_image,
                        file_ids=file_ids,
                        conversation_state=conversation_state,
                        chat_history=chat_history,
                        strict_document_context=strict_document_context,
                    )
                elif detected_intent == CHAT_MODE_AI_ASSISTANT:
                    result = build_ai_assistant_prompt(
                        query=query,
                        chat_history=chat_history,
                        model_name=model_name,
                        conversation_state=conversation_state,
                        file_ids=file_ids,
                        strict_document_context=strict_document_context,
                    )
                elif detected_intent == CHAT_MODE_WEB_SEARCH:
                    result = build_web_search_prompt(
                        query=query,
                        model_name=model_name,
                        chat_history=chat_history,
                        conversation_state=conversation_state,
                        file_ids=file_ids,
                        strict_document_context=strict_document_context,
                    )
                else:
                    result = build_chat_prompt(
                        query=query,
                        file_ids=file_ids,
                        chat_history=chat_history,
                        model_name=model_name,
                        conversation_state=conversation_state,
                    )
            except TechnoChatError:
                raise
            except Exception as e:
                if is_network_error(e):
                    raise NetworkConnectionError(
                        internal=f"Network during mode={chat_mode}. raw={e}"
                    )
                if is_quota_error(e):
                    raise ChatModelQuotaError(
                        internal=f"Quota during mode={chat_mode}. model={model_name} raw={e}"
                    )
                raise ChatResponseError(
                    internal=f"Pipeline failed. mode={chat_mode}. raw={e}"
                )

            prompt     = result["answer"]
            sources    = _normalize_chat_sources(result["sources"], result.get("chat_mode", chat_mode))
            is_greeting = result["is_greeting"]
            is_summary  = result["is_summary"]
            effective_chat_mode = result.get("chat_mode", chat_mode)
            image_urls = result.get("image_urls", [])
            resolved_query = result.get("resolved_query", query)
            selected_model = result.get("selected_model", model_name)
            update_conversation_state(request, session.id, query=query, resolved_query=resolved_query)
            set_last_active_chat_session(request, session.id)

        # ── 5. Save message ───────────────────────────────────────────────────
        try:
            msg = ChatMessage.objects.create(
                session=session,
                question=query,
                answer=prompt,
                model_used=selected_model,
                sources=sources,
                chat_mode=effective_chat_mode,
            )
        except Exception as e:
            if is_network_error(e):
                raise NetworkConnectionError(
                    internal=f"Network during ChatMessage create. session={session_id} raw={e}"
                )
            raise ChatMessageSendError(
                internal=f"ChatMessage create failed. session={session_id} raw={e}"
            )

        # ── 6. Return JSON ────────────────────────────────────────────────────
        return JsonResponse({
            "success": True,
            "message": {
                "id":            msg.id,
                "question":      msg.question,
                "answer":        prompt,
                "model_used":    selected_model,
                "sources":       sources,
                "is_greeting":   is_greeting,
                "is_summary":    is_summary,
                "chat_mode":     effective_chat_mode,
                "image_urls":    image_urls,
                "created_at":    msg.created_at.strftime("%b %d, %Y %I:%M %p"),
                "message_count": ChatMessage.objects.filter(session=session).count(),
            }
        })

    except TechnoChatError as e:
        logger.error(
            "chat_send_view | TechnoChatError: %s | internal: %s",
            e.user_message, e.internal_note
        )
        return JsonResponse({"success": False, "error": e.user_message}, status=400)
    except Exception as e:
        logger.error("chat_send_view | unexpected error: %s", e)
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred while generating the response."},
            status=500,
        )


# =============================================================================
# EXTRA PAGE VIEWS
# =============================================================================

def home_view(request):
    user = _get_user(request)
    if not user:
        return redirect("login")
    return render(request, "home.html", {
        "user": user,
        **_nav_context(user),
    })


def about_view(request):
    user = _get_user(request)
    if not user:
        return redirect("login")
    return render(request, "about_us.html", {
        "user": user,
        "now": timezone.now(),
        **_nav_context(user),
    })


def profile_view(request):
    user = _get_user(request)
    if not user:
        return redirect("login")

    profile = _get_or_create_profile(user)
    error = None

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        surname    = request.POST.get("surname", "").strip()
        username   = request.POST.get("username", "").strip().lower()
        position   = request.POST.get("position_at_technostacks", "").strip()
        team       = request.POST.get("team", "").strip()

        try:
            validate_profile_fields(first_name, surname, username)
            validate_profile_username(username, profile.pk)

            profile.first_name               = first_name
            profile.surname                  = surname
            profile.username                 = username
            profile.position_at_technostacks = position
            profile.team                     = team
            profile.is_profile_complete      = True
            profile.save()
            # Sync completion flag on the User model itself
            if not user.profile_completed:
                user.profile_completed = True
                user.save(update_fields=["profile_completed"])
            return redirect("home")
        except ValidationError as e:
            error = e.message
        except TechnoChatError as e:
            error = e.user_message

    return render(request, "profile.html", {
        "user": user,
        "profile": profile,
        "error": error,
        "team_choices": ContributorTeamChoices.choices,
        **_nav_context(user),
    })


# =============================================================================
# PAGE / SOURCE RENDER VIEW  (new)
# =============================================================================

def page_render_view(request):
    """
    GET /chat/page-render/
    Returns the source content for a given file location.

    For PDF files with a page_index  → renders the page as a PNG image
                                        (with optional yellow text highlight)
                                        and returns its media URL.

    For all other file types          → extracts the relevant text excerpt
                                        (slide text, sheet rows, paragraphs,
                                         lines, or image description) and
                                        returns it as a plain-text string.

    Query params:
        file_id      (required)
        file_type    (required)
        page_index   (optional — 1-based, used for PDF / DOCX)
        slide_index  (optional — 1-based, used for PPTX)
        sheet_name   (optional — used for XLSX)
        row_start    (optional — 1-based, used for XLSX / CSV)
        highlight    (optional — text to highlight on the PDF page)

    Returns JSON:
        {success, image_url, source_type}   when source_type == 'page'
        {success, content_text, source_type} when source_type == 'text'
        {success: false, error}              on failure
    """
    user = _get_user(request)
    if not user:
        return JsonResponse({"success": False, "error": "Not authenticated"}, status=401)

    file_id        = request.GET.get("file_id")
    file_type      = request.GET.get("file_type", "").lower()
    page_index     = request.GET.get("page_index")
    page_end       = request.GET.get("page_end")
    slide_index    = request.GET.get("slide_index")
    sheet_name     = request.GET.get("sheet_name")
    row_start      = request.GET.get("row_start")
    line_start     = request.GET.get("line_start")
    line_end       = request.GET.get("line_end")
    section_name   = request.GET.get("section_name")
    highlight_text = request.GET.get("highlight", "")

    if not file_id:
        return JsonResponse({"success": False, "error": "file_id required"}, status=400)

    def _optional_int(value):
        cleaned = str(value or "").strip().lower()
        if cleaned in {"", "none", "null", "undefined"}:
            return None
        return int(cleaned)

    try:
        normalized_type = normalize_file_type(file_type)
        is_visual_source = normalized_type in {"pdf", "doc", "docx", "ppt", "pptx", "txt", "md", "image", "png", "jpg", "jpeg", "webp", "svg"}

        if is_visual_source:
            image_url = get_visual_render(
                file_id=int(file_id),
                file_type=normalized_type,
                page_index=_optional_int(page_index),
                page_end=_optional_int(page_end),
                slide_index=_optional_int(slide_index),
                line_start=_optional_int(line_start),
                line_end=_optional_int(line_end),
                section_name=section_name if section_name else None,
            )
            return JsonResponse({
                "success":     True,
                "image_url":   image_url,
                "source_type": "page",
            })
        else:
            # All other file types → extract text excerpt
            content = get_source_content(
                file_id=int(file_id),
                file_type=file_type,
                page_index=_optional_int(page_index),
                slide_index=_optional_int(slide_index),
                sheet_name=sheet_name        if sheet_name   else None,
                row_start=_optional_int(row_start),
                line_start=_optional_int(line_start),
                line_end=_optional_int(line_end),
                section_name=section_name    if section_name else None,
                highlight_text=highlight_text,
            )
            return JsonResponse({
                "success":      True,
                "content_text": content,
                "source_type":  "text",
            })

    except TechnoChatError as exc:
        logger.error(
            "page_render_view | %s | %s",
            exc.user_message, exc.internal_note
        )
        try:
            fallback_content = get_source_fallback_content(
                file_id=int(file_id),
                file_type=file_type,
                page_index=_optional_int(page_index),
                slide_index=_optional_int(slide_index),
                sheet_name=sheet_name if sheet_name else None,
                row_start=_optional_int(row_start),
                line_start=_optional_int(line_start),
                line_end=_optional_int(line_end),
                section_name=section_name if section_name else None,
                highlight_text=highlight_text,
            )
            return JsonResponse({
                "success": True,
                "content_text": fallback_content,
                "source_type": "text",
            })
        except Exception:
            return JsonResponse({"success": False, "error": exc.user_message}, status=500)
    except Exception as exc:
        logger.error("page_render_view | unexpected: %s", exc)
        return JsonResponse({"success": False, "error": "Preview unavailable."}, status=500)
