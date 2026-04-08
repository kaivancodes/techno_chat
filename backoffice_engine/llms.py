"""
llms.py
───────
LLM model selection and routing.

Public API
──────────
    get_llm_response(user_prompt, system_prompt, model_name) -> str
"""

from .clients import GeminiClient, GroqClient
from techno_chat.settings import (
    logger,
    GEMINI_LLM_MODELS,
    GROQ_LLM_MODELS,
    MODEL_MAP,
)


def get_llm_response(user_prompt: str, system_prompt: str = None, model_name: str = None) -> str:
    """
    Route a prompt to the correct LLM (Gemini or Groq) based on model_name.
    Defaults to the first Gemini model if model_name is omitted.
    """
    if model_name is None:
        model_name = list(GEMINI_LLM_MODELS.keys())[0]

    if model_name in GEMINI_LLM_MODELS:
        logger.info("get_llm_response | routing to Gemini | model=%s", model_name)
        return GeminiClient().chat(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            llm_model=model_name,
        )
    elif model_name in GROQ_LLM_MODELS:
        logger.info("get_llm_response | routing to Groq | model=%s", model_name)
        return GroqClient().chat(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            llm_model=model_name,
        )
    else:
        raise ValueError(f"Unknown model '{model_name}'. Available: {list(MODEL_MAP.keys())}")
