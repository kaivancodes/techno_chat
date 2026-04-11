import json
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.urls import reverse, NoReverseMatch
from django.db.models import Prefetch
from django.http import HttpRequest
from django.db import IntegrityError
from django.utils.text import capfirst
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.admin import utils as admin_utils

from backoffice_engine.models import AdminUser, AdminProfile, User, UserProfile, File, ChatSession, ChatMessage, check_username
from backoffice_engine.admin_auth import create_admin, _check_email_domain, _check_password_strength
from backoffice_engine.choices import AdminTeamChoices, ContributorTeamChoices, SessionType, FileProcessingStatus
from backoffice_engine.constants import CHAT_MODE_AI_ASSISTANT, CHAT_MODE_IMAGE_GENERATION, CHAT_MODE_RAG, CHAT_MODE_WEB_SEARCH

CHAT_MODE_CHOICES = (
    (CHAT_MODE_AI_ASSISTANT, "AI Assistant"),
    (CHAT_MODE_IMAGE_GENERATION, "Create Image"),
    (CHAT_MODE_RAG, "Chat with File"),
    (CHAT_MODE_WEB_SEARCH, "Web Search"),
)

SECTION_ORDER = (
    "admins",
    "admin_profiles",
    "contributors",
    "profiles",
    "files",
    "sessions",
    "messages",
)


# =========================
# ADMIN LOGIN
# =========================
def admin_login_view(request):
    error = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not email or not password:
            error = "All fields are required."

        else:
            user = authenticate(request, username=email, password=password)

            if user is None:
                error = "Invalid email or password."
            elif not user.is_staff:
                error = "You do not have admin access."
            else:
                login(request, user)
                request.session['role'] = 'admin'
                request.session['tc_admin_id'] = user.id
                
                # Check profile completion
                if hasattr(user, 'admin_profile') and not user.admin_profile.is_profile_complete:
                    return redirect('admin_profile')
                    
                return redirect('admin_dashboard')

    return render(request, "admin/admin_login.html", {"error": error})


# =========================
# ADMIN REGISTER
# =========================
def admin_register_view(request):
    error = None
    success = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm_password", "")

        if not email or not password or not confirm:
            error = "All fields are required."

        elif password != confirm:
            error = "Passwords do not match."

        elif AdminUser.objects.filter(email=email).exists():
            error = "Email id exists."

        else:
            try:
                create_admin(email, password)
                success = "Account created successfully! Redirecting in 3 seconds..."

            except ValidationError as e:
                error = e.message if hasattr(e, 'message') else str(e)

    return render(request, "admin/admin_register.html", {
        "error": error,
        "success": success
    })





# =========================
# ADMIN LOGOUT
# =========================
def admin_logout_view(request):
    logout(request)
    if 'tc_admin_id' in request.session:
        del request.session['tc_admin_id']
    if 'role' in request.session:
        del request.session['role']
    request.session.flush()
    return redirect("admin_login")


# =========================
# ADMIN PROFILE
# =========================
def admin_profile_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("admin_login")

    error = None
    profile = getattr(request.user, 'admin_profile', None)

    if not profile:
        error = "Admin profile not found."
        return render(request, "admin/admin_profile_complete.html", {"error": error})

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        surname = request.POST.get("surname", "").strip()
        username = request.POST.get("username", "").strip()
        position = request.POST.get("position", "").strip()
        team = request.POST.get("team", "").strip()  # Should be Core or HR

        if not all([first_name, surname, username, position, team]):
            error = "All fields are required."
        else:
            try:
                profile.first_name = first_name
                profile.surname = surname
                profile.username = username
                profile.position_at_technostacks = position
                profile.team = team
                profile.is_profile_complete = True
                profile.save()

                request.user.profile_completed = True
                request.user.save()

                return redirect("admin_dashboard")
            except Exception as e:
                error = str(e)

    return render(request, "admin/admin_profile_complete.html", {
        "profile": profile,
        "error": error
    })




def _truthy(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def _sorted_choices(choices):
    return sorted(choices, key=lambda item: item[1].lower())


def _admin_shadow_queryset():
    return User.objects.filter(email__in=AdminUser.objects.values_list("email", flat=True))


def _contributor_queryset():
    return (
        User.objects.exclude(email__in=AdminUser.objects.values_list("email", flat=True))
        .order_by("-created_at", "-id")
    )


def _profile_queryset():
    return (
        UserProfile.objects.select_related("user")
        .exclude(user__email__in=AdminUser.objects.values_list("email", flat=True))
        .order_by("-created_at", "-id")
    )


def _base_queryset_for_section(section: str):
    if section == "admins":
        return AdminUser.objects.select_related("admin_profile").order_by("-date_joined", "-id")
    if section == "admin_profiles":
        return AdminProfile.objects.select_related("admin").order_by("-created_at", "-id")
    if section == "contributors":
        return _contributor_queryset()
    if section == "profiles":
        return _profile_queryset()
    if section == "files":
        return File.objects.select_related("user", "user__profile").order_by("-created_at", "-id")
    if section == "sessions":
        return (
            ChatSession.objects.select_related("user", "user__profile")
            .prefetch_related(
                Prefetch(
                    "files",
                    queryset=File.objects.select_related("user").order_by("original_filename", "id"),
                )
            )
            .order_by("-created_at", "-id")
        )
    if section == "messages":
        return (
            ChatMessage.objects.select_related("session", "session__user", "session__user__profile")
            .order_by("-created_at", "-id")
        )
    return _base_queryset_for_section("admins")


def _section_meta(section: str):
    return {
        "admins": {"title": "Admin", "list_title": "Admins", "total_label": "Admins"},
        "admin_profiles": {"title": "Admin Profile", "list_title": "Admin Profiles", "total_label": "Admin Profiles"},
        "contributors": {"title": "Contributor", "list_title": "Contributors", "total_label": "Contributors"},
        "profiles": {"title": "Profile", "list_title": "Profiles", "total_label": "Profiles"},
        "files": {"title": "File", "list_title": "Files", "total_label": "Files"},
        "sessions": {"title": "Session", "list_title": "Sessions", "total_label": "Sessions"},
        "messages": {"title": "Message", "list_title": "Messages", "total_label": "Messages"},
    }.get(section, {"title": "Admin", "list_title": "Admins", "total_label": "Admins"})


def _section_model(section: str):
    return {
        "admins": AdminUser,
        "admin_profiles": AdminProfile,
        "contributors": User,
        "profiles": UserProfile,
        "files": File,
        "sessions": ChatSession,
        "messages": ChatMessage,
    }.get(section, AdminUser)


def _reverse_history_url(obj):
    try:
        return reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_history",
            args=[obj.pk],
        )
    except NoReverseMatch:
        return "#"


def _dashboard_history_url(section: str, record, show_history: bool) -> str:
    url = reverse("admin_dashboard")
    if show_history:
        return f"{url}?section={section}&edit_id={record.pk}&history=1"
    return f"{url}?section={section}&edit_id={record.pk}"


def _record_heading(section: str, record):
    if section == "admins":
        return f"Details of {record.email}"
    if section == "admin_profiles":
        return f"Profile of {record.get_display_name()}"
    if section == "contributors":
        return f"Details of {record.email}"
    if section == "profiles":
        return f"Profile of {record.get_display_name()}"
    if section == "files":
        return f"File: {record.original_filename or record.file.name}"
    if section == "sessions":
        return f"Session: {record.title}"
    if section == "messages":
        return f"Question: {record.question[:80]}"
    return str(record)


def _format_source_location(item: dict) -> str:
    if item.get("section_name"):
        return f"section {item['section_name']}"
    if item.get("slide_index") is not None:
        return f"slide {item['slide_index']}"
    if item.get("sheet_name") and item.get("row_start") is not None:
        row_end = item.get("row_end")
        if row_end and row_end != item["row_start"]:
            return f"{item['sheet_name']} rows {item['row_start']}-{row_end}"
        return f"{item['sheet_name']} row {item['row_start']}"
    if item.get("row_start") is not None:
        row_end = item.get("row_end")
        if row_end and row_end != item["row_start"]:
            return f"rows {item['row_start']}-{row_end}"
        return f"row {item['row_start']}"
    if item.get("line_start") is not None:
        line_end = item.get("line_end")
        if line_end and line_end != item["line_start"]:
            return f"lines {item['line_start']}-{line_end}"
        return f"line {item['line_start']}"
    if item.get("page_index") is not None:
        page_end = item.get("page_end")
        if page_end and page_end != item["page_index"]:
            return f"page {item['page_index']}-{page_end}"
        return f"page {item['page_index']}"
    return ""


def _format_sources_for_edit(sources, chat_mode: str = ""):
    if not sources:
        return "[]"

    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except json.JSONDecodeError:
            return str(sources)

    if isinstance(sources, dict):
        sources = [sources]

    if not isinstance(sources, list):
        return "[]"

    if chat_mode in {CHAT_MODE_AI_ASSISTANT, CHAT_MODE_IMAGE_GENERATION}:
        return "[]"

    formatted = []
    for item in sources:
        if isinstance(item, dict):
            kind = item.get("kind", "")
            if kind in {"generated_image", "uploaded_image"}:
                continue

            link = item.get("link", "").strip()
            if link:
                formatted.append(link)
                continue

            file_name = item.get("file_name", "").strip()
            if file_name:
                location = _format_source_location(item)
                formatted.append(f"{file_name} {location}".strip())
        elif isinstance(item, str):
            formatted.append(item)

    if not formatted:
        return "[]"

    return "[" + ", ".join(formatted) + "]"


def _history_entries_for_object(obj):
    content_type = admin_utils.get_content_type_for_model(obj, for_concrete_model=False)
    entries = (
        LogEntry.objects.filter(content_type=content_type, object_id=str(obj.pk))
        .select_related("user")
        .order_by("-action_time")
    )

    action_map = {
        ADDITION: ("Created", "success"),
        CHANGE: ("Updated", "info"),
        DELETION: ("Deleted", "danger"),
    }

    history_entries = []
    for entry in entries:
        label, tone = action_map.get(entry.action_flag, ("Changed", "info"))
        history_entries.append(
            {
                "label": label,
                "tone": tone,
                "time": entry.action_time,
                "user": getattr(entry.user, "email", "System") if entry.user_id else "System",
                "message": entry.get_change_message() or "No extra details available.",
            }
        )

    return history_entries


def _log_admin_change(user, obj, field_names):
    LogEntry.objects.log_actions(
        user_id=user.pk,
        queryset=[obj],
        action_flag=CHANGE,
        change_message=[{"changed": {"name": capfirst(obj._meta.verbose_name), "object": str(obj), "fields": field_names}}],
        single_object=True,
    )


def _log_admin_addition(user, obj):
    LogEntry.objects.log_actions(
        user_id=user.pk,
        queryset=[obj],
        action_flag=ADDITION,
        change_message=[{"added": {"name": capfirst(obj._meta.verbose_name), "object": str(obj)}}],
        single_object=True,
    )


def _log_admin_deletion(user, model, object_id, object_repr):
    try:
        LogEntry.objects.log_action(
            user_id=user.pk,
            content_type_id=admin_utils.get_content_type_for_model(model).pk,
            object_id=object_id,
            object_repr=object_repr,
            action_flag=DELETION,
            change_message=[{"deleted": {"name": capfirst(model._meta.verbose_name), "object": object_repr}}],
        )
    except Exception:
        pass


def _clean_team(value, choices, label):
    valid_values = {choice_value for choice_value, _ in choices}
    if value not in valid_values:
        raise ValidationError(f"Please choose a valid {label}.")
    return value


def _clean_unique_username(value, current_profile, peer_model):
    username = value.strip()
    check_username(username)

    if peer_model.objects.filter(username__iexact=username).exclude(pk=current_profile.pk).exists():
        raise ValidationError("This username is already taken.")

    sibling_model = AdminProfile if peer_model is UserProfile else UserProfile
    if sibling_model.objects.filter(username__iexact=username).exists():
        raise ValidationError("This username is already taken.")

    return username





def _save_admin(record: AdminUser, data):
    old_email = record.email
    new_email = data.get("email", "").strip().lower()
    if not new_email:
        raise ValidationError("Email is required.")
    _check_email_domain(new_email)

    if AdminUser.objects.filter(email__iexact=new_email).exclude(pk=record.pk).exists():
        raise ValidationError("Email already exists in Admins.")

    if _contributor_queryset().filter(email__iexact=new_email).exists():
        raise ValidationError("This email already exists in Contributors.")

    record.email = new_email
    record.profile_completed = _truthy(data.get("profile_completed"))
    record.is_staff = True
    record.is_superuser = True
    record.save()

    return ["email", "profile completed"]


def _save_contributor(record: User, data):
    new_email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not new_email:
        raise ValidationError("Email is required.")

    _check_email_domain(new_email)

    if User.objects.filter(email__iexact=new_email).exclude(pk=record.pk).exists():
        raise ValidationError("Email already exists in Contributors.")
    if AdminUser.objects.filter(email__iexact=new_email).exists():
        raise ValidationError("This email already exists in Admins.")

    record.email = new_email
    record.profile_completed = _truthy(data.get("profile_completed"))

    changed_fields = ["email", "profile_completed"]

    # Only update password if a new one was explicitly provided
    if password:
        _check_password_strength(password)
        record.password = password
        changed_fields.append("password")

    record.save()
    return changed_fields


def _save_admin_profile(record: AdminProfile, data):
    first_name = data.get("first_name", "").strip()
    surname = data.get("surname", "").strip()
    username = _clean_unique_username(data.get("username", ""), record, AdminProfile)
    position = data.get("position_at_technostacks", "").strip()
    team = _clean_team(data.get("team", "").strip(), AdminTeamChoices.choices, "team")

    if not all([first_name, surname, username, position, team]):
        raise ValidationError("All profile fields are required.")

    record.first_name = first_name
    record.surname = surname
    record.username = username
    record.position_at_technostacks = position
    record.team = team
    record.is_profile_complete = True
    record.save()

    if record.admin.profile_completed is not True:
        record.admin.profile_completed = True
        record.admin.save(update_fields=["profile_completed"])

    return ["first name", "surname", "username", "position", "team"]


def _save_profile(record: UserProfile, data):
    first_name = data.get("first_name", "").strip()
    surname = data.get("surname", "").strip()
    username = _clean_unique_username(data.get("username", ""), record, UserProfile)
    position = data.get("position_at_technostacks", "").strip()
    team = _clean_team(data.get("team", "").strip(), ContributorTeamChoices.choices, "team")

    if not all([first_name, surname, username, position, team]):
        raise ValidationError("All profile fields are required.")

    record.first_name = first_name
    record.surname = surname
    record.username = username
    record.position_at_technostacks = position
    record.team = team
    record.is_profile_complete = True
    record.save()

    if record.user.profile_completed is not True:
        record.user.profile_completed = True
        record.user.save(update_fields=["profile_completed"])

    return ["first name", "surname", "username", "position", "team"]


def _save_file(record: File, data):
    status = data.get("embedding_status", "").strip()
    if status not in {value for value, _ in FileProcessingStatus.choices}:
        raise ValidationError("Please choose a valid status.")

    original_filename = data.get("original_filename", "").strip()
    if not original_filename:
        raise ValidationError("Original file name is required.")

    record.original_filename = original_filename
    record.embedding_status = status
    record.save()
    return ["original file name", "status"]


def _save_session(record: ChatSession, data):
    title = data.get("title", "").strip()
    session_type = data.get("session_type", "").strip()
    if not title:
        raise ValidationError("Title is required.")
    if session_type not in {value for value, _ in SessionType.choices}:
        raise ValidationError("Please choose a valid chat type.")

    record.title = title
    record.session_type = session_type
    record.save()

    if session_type == SessionType.GENERAL_CHAT:
        record.files.clear()
    else:
        file_ids = data.getlist("file_ids")
        allowed_files = File.objects.filter(user=record.user, pk__in=file_ids).order_by("id")
        record.files.set(allowed_files)

    return ["title", "chat type", "files"]


def _save_message(record: ChatMessage, data):
    question = data.get("question", "").strip()
    answer = data.get("answer", "").strip()
    model_used = data.get("model_used", "").strip()
    chat_mode = data.get("chat_mode", "").strip()

    if not question:
        raise ValidationError("Question is required.")
    if not answer:
        raise ValidationError("Answer is required.")
    if not model_used:
        raise ValidationError("Model used is required.")
    if chat_mode not in {value for value, _ in CHAT_MODE_CHOICES}:
        raise ValidationError("Please choose a valid chat mode.")

    record.question = question
    record.answer = answer
    record.model_used = model_used
    record.chat_mode = chat_mode
    record.save()
    return ["question", "answer", "model used", "chat mode"]


def _save_record(section, record, data):
    if section == "admins":
        return _save_admin(record, data)
    if section == "contributors":
        return _save_contributor(record, data)
    if section == "admin_profiles":
        return _save_admin_profile(record, data)
    if section == "profiles":
        return _save_profile(record, data)
    if section == "files":
        return _save_file(record, data)
    if section == "sessions":
        return _save_session(record, data)
    if section == "messages":
        return _save_message(record, data)
    raise ValidationError("Invalid section.")


def _prepare_context(section, records, edit_record=None, show_history=False):
    meta = _section_meta(section)
    table_colspan = {
        "admins": 3,
        "admin_profiles": 4,
        "contributors": 3,
        "profiles": 4,
        "files": 5,
        "sessions": 5,
        "messages": 6,
    }.get(section, 3)
    context = {
        "section": section,
        "section_meta": meta,
        "section_order": SECTION_ORDER,
        "records": records,
        "record_count": records.count() if records is not None else 0,
        "table_colspan": table_colspan,
        "admin_team_choices": _sorted_choices(AdminTeamChoices.choices),
        "contributor_team_choices": _sorted_choices(ContributorTeamChoices.choices),
        "session_type_choices": SessionType.choices,
        "file_status_choices": FileProcessingStatus.choices,
        "chat_mode_choices": CHAT_MODE_CHOICES,
        "show_contributor_success_popup": False,
        "choices": {
            "AdminTeamChoices": _sorted_choices(AdminTeamChoices.choices),
            "ContributorTeamChoices": _sorted_choices(ContributorTeamChoices.choices),
            "SessionType": SessionType.choices,
            "FileProcessingStatus": FileProcessingStatus.choices,
        }
    }

    if edit_record is not None:
        file_choices = []
        if section == "sessions":
            file_choices = File.objects.filter(user=edit_record.user).order_by("original_filename", "id")

        history_entries = _history_entries_for_object(edit_record) if show_history else []
        context.update(
            {
                "edit_id": edit_record.pk,
                "edit_record": edit_record,
                "edit_heading": _record_heading(section, edit_record),
                "history_url": _dashboard_history_url(section, edit_record, not show_history),
                "history_button_label": "Hide History" if show_history else "History",
                "show_history": show_history,
                "history_entries": history_entries,
                "session_file_choices": file_choices,
                "edit_record_sources_display": _format_sources_for_edit(
                    getattr(edit_record, "sources", None),
                    getattr(edit_record, "chat_mode", ""),
                ),
            }
        )

    return context


def admin_dashboard_view(request: HttpRequest):
    if not request.session.get('tc_admin_id'):
        return redirect('admin_login')
    request.user = AdminUser.objects.get(id=request.session['tc_admin_id'])
    profile = getattr(request.user, "admin_profile", None)
    if profile and not profile.is_profile_complete:
        return redirect("admin_profile")

    section = request.GET.get("section", "admins")
    if section not in SECTION_ORDER:
        section = "admins"

    queryset = _base_queryset_for_section(section)
    edit_id = request.GET.get("edit_id")

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        try:
            if action == "delete_bulk":
                selected_ids = [value for value in request.POST.getlist("record_ids") if value]
                objects = list(queryset.filter(pk__in=selected_ids))

                if section == "admins":
                    objects = [obj for obj in objects if obj.pk != request.user.pk]
                    if len(selected_ids) != len(objects):
                        messages.error(request, "You cannot delete the admin account currently signed in.")

                deleted_emails = [obj.email for obj in objects if section == "admins"]
                deleted_rows = [(obj.pk, str(obj)) for obj in objects]
                deleted_count = len(objects)

                for object_id, object_repr in deleted_rows:
                    _log_admin_deletion(request.user, _section_model(section), object_id, object_repr)

                if deleted_count:
                    queryset.filter(pk__in=[obj.pk for obj in objects]).delete()
                    messages.success(request, f"{deleted_count} {section.replace('_', ' ')} deleted successfully.")
                else:
                    messages.error(request, "Select at least one row to delete.")

                return redirect(f"{reverse('admin_dashboard')}?section={section}")

            if action in {"edit_save", "delete_single"} and edit_id:
                record = get_object_or_404(queryset, pk=edit_id)

                if action == "delete_single":
                    if section == "admins" and record.pk == request.user.pk:
                        messages.error(request, "You cannot delete the admin account currently signed in.")
                        return redirect(f"{reverse('admin_dashboard')}?section={section}&edit_id={record.pk}")

                    _log_admin_deletion(request.user, record.__class__, record.pk, str(record))
                    record.delete()
                    messages.success(request, f"{_section_meta(section)['title']} deleted successfully.")
                    return redirect(f"{reverse('admin_dashboard')}?section={section}")

                changed_fields = _save_record(section, record, request.POST)
                _log_admin_change(request.user, record, changed_fields)
                messages.success(request, f"{_section_meta(section)['title']} updated successfully.")
                return redirect(f"{reverse('admin_dashboard')}?section={section}&edit_id={record.pk}")

        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, "message") else str(exc))
        except IntegrityError:
            messages.error(request, "This change would create a duplicate entry.")
        except Exception as exc:
            messages.error(request, str(exc))

    if edit_id:
        edit_record = get_object_or_404(queryset, pk=edit_id)
        context = _prepare_context(
            section,
            queryset,
            edit_record=edit_record,
            show_history=request.GET.get("history") == "1",
        )
    else:
        context = _prepare_context(section, queryset)

    context["show_contributor_success_popup"] = request.GET.get("contributor_added") == "1"
    return render(request, "admin/admin_dashboard.html", context)


def admin_new_contributor_view(request: HttpRequest):
    if not request.session.get('tc_admin_id'):
        return redirect('admin_login')
    request.user = AdminUser.objects.get(id=request.session['tc_admin_id'])
    profile = getattr(request.user, "admin_profile", None)
    if profile and not profile.is_profile_complete:
        return redirect("admin_profile")

    if request.method != "POST":
        return redirect(f"{reverse('admin_dashboard')}?section=contributors")

    try:
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        position = request.POST.get("position", "").strip()
        team = request.POST.get("team", "").strip()

        if not all([email, password, position, team]):
            raise ValidationError("All contributor fields are required.")

        _check_email_domain(email)
        _check_password_strength(password)
        _clean_team(team, ContributorTeamChoices.choices, "team")

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Email already exists in Contributors.")
        if AdminUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email already exists in Admins.")

        contributor = User.objects.create(
            email=email,
            password=password,
            profile_completed=False,
        )
        profile = UserProfile.objects.create(
            user=contributor,
            position_at_technostacks=position,
            team=team,
            is_profile_complete=False,
        )
        _log_admin_addition(request.user, contributor)
        _log_admin_addition(request.user, profile)
        messages.success(request, "Contributor added successfully.")
        return redirect(f"{reverse('admin_dashboard')}?section=contributors&contributor_added=1")

    except ValidationError as exc:
        messages.error(request, exc.message if hasattr(exc, "message") else str(exc))
    except IntegrityError:
        messages.error(request, "This contributor already exists.")
    except Exception as exc:
        messages.error(request, str(exc))

    return redirect(f"{reverse('admin_dashboard')}?section=contributors")
