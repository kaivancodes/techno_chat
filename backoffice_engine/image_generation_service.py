"""
image_generation_service.py
───────────────────────────
Text-to-image and image-to-image orchestration.
"""

from .helpers import filename_from_url
from .clients import KieImageClient
from .constants import CHAT_MODE_IMAGE_GENERATION, DOCUMENT_SCOPE_RESPONSE
from .exceptions import ChatResponseError
from .image_processing_service import save_generated_image, save_uploaded_image, uploaded_image_to_data_uri
from .retrieval_service import build_document_context_text
from techno_chat.settings import logger


def _display_model_name(model_name: str, is_edit: bool) -> str:
    return "GPT 1 Image" if is_edit else "GPT 1.5 Image"


def build_image_generation_prompt(
    query: str,
    request,
    uploaded_image=None,
    file_ids: list | None = None,
    conversation_state: dict | None = None,
    chat_history: list | None = None,
    strict_document_context: bool = False,
) -> dict:
    if not query:
        raise ChatResponseError("Please enter a prompt before sending.")

    client = KieImageClient()
    if not client.api_key or not client.text_model or not client.edit_model:
        raise ChatResponseError("Image generation is not configured properly.")
    image_urls = []
    sources = []
    prompt_query = query
    strict_document_context = strict_document_context or bool(file_ids)

    if strict_document_context:
        document_context = build_document_context_text(
            query=query,
            file_ids=file_ids or [],
            chat_history=chat_history or [],
            conversation_state=conversation_state or {},
            max_chunks=4,
            token_budget=1000,
        )
        if not document_context:
            return {
                "answer": DOCUMENT_SCOPE_RESPONSE,
                "sources": [],
                "is_greeting": False,
                "is_summary": False,
                "chat_mode": CHAT_MODE_IMAGE_GENERATION,
                "image_urls": [],
                "selected_model": _display_model_name(client.edit_model if uploaded_image is not None else client.text_model, is_edit=uploaded_image is not None),
                "resolved_query": query,
            }
        prompt_query = (
            "Create the image using only this uploaded document context.\n"
            f"Document context:\n{document_context}\n\n"
            f"User request: {query}\n"
            "Do not introduce details that are not supported by the document context."
        )

    try:
        if uploaded_image is not None:
            # Reset stream so both save and data-URI functions read from the start
            if hasattr(uploaded_image, "seek"):
                uploaded_image.seek(0)
            relative_url = save_uploaded_image(uploaded_image)
            logger.info("build_image_generation_prompt | mode=image_to_image")
            image_inputs = [uploaded_image_to_data_uri(uploaded_image)]
            public_url = request.build_absolute_uri(relative_url)
            logger.info(
                "build_image_generation_prompt | image_inputs count=%s | edit_model=%s",
                len(image_inputs), client.edit_model,
            )
            image_urls = client.image_to_image(prompt_query, image_inputs)
            sources.append({
                "kind": "uploaded_image",
                "title": "Input Image",
                "link": public_url,
                "image_url": relative_url,
            })
            selected_model = _display_model_name(client.edit_model, is_edit=True)
            answer = "Here is the edited image."
        else:
            logger.info("build_image_generation_prompt | mode=text_to_image")
            image_urls = client.text_to_image(prompt_query)
            selected_model = _display_model_name(client.text_model, is_edit=False)
            answer = "Here is the generated image."
    except TimeoutError as exc:
        logger.error("build_image_generation_prompt | TimeoutError: %s", exc)
        raise ChatResponseError("Image generation is taking longer than expected. Please try again.") from exc
    except ValueError as exc:
        logger.error("build_image_generation_prompt | ValueError: %s", exc)
        raise ChatResponseError("Image generation failed. Please try again.") from exc

    if not image_urls:
        raise ChatResponseError("Image generation failed. Please try again.")

    saved_image_urls = []
    for index, url in enumerate(image_urls, start=1):
        try:
            local_url, saved_file_path = save_generated_image(url)
        except Exception as exc:
            logger.warning("build_image_generation_prompt | generated image save failed | raw=%s", exc)
            local_url = url
            saved_file_path = ""
        saved_image_urls.append(local_url)
        sources.append({
            "kind": "generated_image",
            "title": filename_from_url(local_url, fallback=f"generated-image-{index}.png"),
            "link": local_url,
            "image_url": local_url,
            "download_url": local_url,
            "local_path": local_url,
            "saved_file_path": saved_file_path,
        })

    return {
        "answer": answer,
        "sources": sources,
        "is_greeting": False,
        "is_summary": False,
        "chat_mode": CHAT_MODE_IMAGE_GENERATION,
        "image_urls": saved_image_urls,
        "selected_model": selected_model,
        "resolved_query": query,
    }
