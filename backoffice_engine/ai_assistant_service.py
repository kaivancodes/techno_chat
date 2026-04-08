"""
ai_assistant_service.py
───────────────────────
AI Assistant Mode pipeline: answers using model knowledge with controlled history.
"""

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .clients import GeminiClient, GroqClient
from .constants import CHAT_HISTORY_COUNT, CHAT_MODE_AI_ASSISTANT
from .prompts import AI_ASSISTANT_SYSTEM_PROMPT
from .query_service import (
    build_query_variations,
    contains_offensive_language,
    get_resolved_query_text,
    is_greeting_query,
    should_include_history_in_answer,
    should_refuse_for_abuse,
    split_multi_question,
    strip_offensive_language,
)
from .response_parsing_service import extract_json_candidate, parse_json_dict
from techno_chat.settings import GEMINI_LLM_MODELS, logger


GREETING_RESPONSE = "Hi! How can I help you today?"
RESPECTFUL_RESPONSE = "Please keep our conversation respectful and I will be happy to help you."


def build_ai_assistant_prompt(query: str, chat_history: list, model_name: str, conversation_state: dict | None = None) -> dict:
    logger.info("build_ai_assistant_prompt | query_len=%s model=%s", len(query), model_name)

    if should_refuse_for_abuse(query):
        return {
            "answer": RESPECTFUL_RESPONSE,
            "sources": [],
            "is_greeting": False,
            "is_summary": False,
            "chat_mode": CHAT_MODE_AI_ASSISTANT,
            "resolved_query": "",
        }

    cleaned_query = strip_offensive_language(query) if contains_offensive_language(query) else query
    if is_greeting_query(cleaned_query, chat_history):
        return {
            "answer": GREETING_RESPONSE,
            "sources": [],
            "is_greeting": True,
            "is_summary": False,
            "chat_mode": CHAT_MODE_AI_ASSISTANT,
            "resolved_query": cleaned_query,
        }

    state = conversation_state or {}
    use_history = should_include_history_in_answer(cleaned_query)
    lc_history = _build_history(chat_history) if use_history else []
    question_parts = split_multi_question(cleaned_query)
    llm = _select_llm(model_name)
    focus_context = _focus_context(state)

    prompt = ChatPromptTemplate.from_messages([
        ("system", AI_ASSISTANT_SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "Conversation focus: {focus_context}\nQuestion: {input}\nReturn valid JSON only with this shape:\n{{\"answer\": \"final answer here\"}}"),
    ])
    chain = prompt | llm

    answers = []
    resolved_queries = []
    for question_part in question_parts:
        query_variations = build_query_variations(
            question_part,
            chat_history=chat_history,
            active_topic=state.get("active_topic", ""),
            active_entities=state.get("active_entities", []),
        )
        logger.info("build_ai_assistant_prompt | refactored_queries=%s", query_variations)
        if not query_variations:
            continue

        resolved_query = get_resolved_query_text(
            question_part,
            chat_history=chat_history,
            active_topic=state.get("active_topic", ""),
            active_entities=state.get("active_entities", []),
        )
        resolved_queries.append(resolved_query)

        response = chain.invoke({
            "input": resolved_query,
            "focus_context": focus_context,
            "chat_history": lc_history,
        })
        raw_answer = response.content if hasattr(response, "content") else str(response)
        answers.append(_parse_assistant_answer(raw_answer))

    final_answer = "\n\n".join(answer for answer in answers if answer).strip()
    return {
        "answer": final_answer or "I’m not sure.",
        "sources": [],
        "is_greeting": False,
        "is_summary": False,
        "chat_mode": CHAT_MODE_AI_ASSISTANT,
        "resolved_query": resolved_queries[0] if resolved_queries else cleaned_query,
    }


def _build_history(chat_history: list) -> list:
    history = []
    limited_history = chat_history[-CHAT_HISTORY_COUNT:]
    for message in limited_history:
        history.append(HumanMessage(content=message.question))
        history.append(AIMessage(content=message.answer))
    return history


def _parse_assistant_answer(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""

    payload = parse_json_dict(text)
    if isinstance(payload, dict):
        return str(payload.get("answer", "")).strip()
    return extract_json_candidate(text) or text


def _select_llm(model_name: str):
    if model_name in GEMINI_LLM_MODELS:
        return GeminiClient().get_llm(model_name)
    return GroqClient().get_llm(model_name)


def _focus_context(state: dict) -> str:
    topic = (state or {}).get("active_topic", "") or "No active topic"
    entities = ", ".join((state or {}).get("active_entities", [])[:5])
    if entities:
        return f"Stay anchored to: {topic}. Important entities: {entities}."
    return f"Stay anchored to: {topic}."
