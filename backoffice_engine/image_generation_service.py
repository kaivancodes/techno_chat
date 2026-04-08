"""
image_generation_service.py
───────────────────────────
Text-to-image and image-to-image orchestration.
"""

from .clients import KieImageClient
from .constants import CHAT_MODE_IMAGE_GENERATION
from .exceptions import ChatResponseError
from .image_processing_service import save_uploaded_image, uploaded_image_to_data_uri
from techno_chat.settings import logger


def build_image_generation_prompt(query: str, request, uploaded_image=None) -> dict:
    if not query:
        raise ChatResponseError("Please enter a prompt before sending.")

    client = KieImageClient()
    if not client.api_key or not client.text_model or not client.edit_model:
        raise ChatResponseError("Image generation is not configured properly.")
    image_urls = []
    sources = []

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
            image_urls = client.image_to_image(query, image_inputs)
            sources.append({
                "kind": "uploaded_image",
                "title": "Input Image",
                "link": public_url,
                "image_url": relative_url,
            })
            selected_model = client.edit_model
            answer = "Here is the edited image."
        else:
            logger.info("build_image_generation_prompt | mode=text_to_image")
            image_urls = client.text_to_image(query)
            selected_model = client.text_model
            answer = "Here is the generated image."
    except TimeoutError as exc:
        logger.error("build_image_generation_prompt | TimeoutError: %s", exc)
        raise ChatResponseError("Image generation is taking longer than expected. Please try again.") from exc
    except ValueError as exc:
        logger.error("build_image_generation_prompt | ValueError: %s", exc)
        raise ChatResponseError("Image generation failed. Please try again.") from exc

    if not image_urls:
        raise ChatResponseError("Image generation failed. Please try again.")

    for index, url in enumerate(image_urls, start=1):
        sources.append({
            "kind": "generated_image",
            "title": f"Generated Image {index}",
            "link": url,
            "image_url": url,
        })

    return {
        "answer": answer,
        "sources": sources,
        "is_greeting": False,
        "is_summary": False,
        "chat_mode": CHAT_MODE_IMAGE_GENERATION,
        "image_urls": image_urls,
        "selected_model": selected_model,
        "resolved_query": query,
    }
