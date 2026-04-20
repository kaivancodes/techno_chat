"""
web_search_service.py
─────────────────────
Web Search Mode pipeline: refactor query, search, and synthesize with source control.
"""

from langchain_core.messages import HumanMessage, SystemMessage

from .clients import GeminiClient, GroqClient, SerperClient
from .constants import CHAT_MODE_WEB_SEARCH, WEB_SEARCH_CONTENT_SNIPPET_LEN
from .exceptions import WebSearchError
from .prompts import WEB_SEARCH_SYNTHESIS_PROMPT
from .query_service import (
    build_query_variations,
    contains_offensive_language,
    get_resolved_query_text,
    is_greeting_query,
    should_refuse_for_abuse,
    split_multi_question,
    strip_offensive_language,
)
from .helpers import extract_urls_from_text
from .retrieval_service import build_document_context_text
from .response_parsing_service import extract_json_candidate, parse_json_dict
from techno_chat.settings import GEMINI_LLM_MODELS, logger


GREETING_RESPONSE = "Hi! How can I help you today?"
RESPECTFUL_RESPONSE = "Please keep our conversation respectful and I will be happy to help you."


def build_web_search_prompt(
    query: str,
    model_name: str,
    chat_history: list | None = None,
    conversation_state: dict | None = None,
    file_ids: list | None = None,
) -> dict:
    logger.info("build_web_search_prompt | query_len=%s model=%s", len(query), model_name)

    if should_refuse_for_abuse(query):
        return {
            "answer": RESPECTFUL_RESPONSE,
            "sources": [],
            "is_greeting": False,
            "is_summary": False,
            "chat_mode": CHAT_MODE_WEB_SEARCH,
            "resolved_query": "",
        }

    cleaned_query = strip_offensive_language(query) if contains_offensive_language(query) else query
    if is_greeting_query(cleaned_query, chat_history):
        return {
            "answer": GREETING_RESPONSE,
            "sources": [],
            "is_greeting": True,
            "is_summary": False,
            "chat_mode": CHAT_MODE_WEB_SEARCH,
            "resolved_query": cleaned_query,
        }

    llm = _select_llm(model_name)
    state = conversation_state or {}
    question_parts = split_multi_question(cleaned_query)
    focus_context = _focus_context(state)
    document_context = build_document_context_text(
        query=cleaned_query,
        file_ids=file_ids or [],
        chat_history=chat_history or [],
        conversation_state=state,
        max_chunks=3,
        token_budget=900,
    )

    answers = []
    used_sources = []
    resolved_queries = []

    for question_part in question_parts:
        query_variations = build_query_variations(
            question_part,
            chat_history=chat_history,
            active_topic=state.get("active_topic", ""),
            active_entities=state.get("active_entities", []),
        )
        logger.info("build_web_search_prompt | refactored_queries=%s", query_variations)
        if not query_variations:
            continue

        resolved_query = get_resolved_query_text(
            question_part,
            chat_history=chat_history,
            active_topic=state.get("active_topic", ""),
            active_entities=state.get("active_entities", []),
        )
        resolved_queries.append(resolved_query)

        results = SerperClient().search(resolved_query)
        if not results:
            raise WebSearchError(internal=f"No results returned for query: {resolved_query[:80]}")

        formatted_results = _format_results(results)
        response = llm.invoke([
            SystemMessage(content=WEB_SEARCH_SYNTHESIS_PROMPT.format(search_results=formatted_results)),
            HumanMessage(content="Conversation focus: " + focus_context + "\nDocument context: " + (document_context or "No active document context.") + "\nQuestion: " + question_part + "\nReturn valid JSON only with this shape:\n{{\"answer\": \"final answer here\", \"used_result_ids\": [1, 2]}}"),
        ])
        raw_answer = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_web_answer(raw_answer)
        answers.append(parsed["answer"])
        part_sources = _select_web_sources(results, parsed["used_result_ids"])
        for source in part_sources:
            if source not in used_sources:
                used_sources.append(source)

    final_answer = "\n\n".join(answer for answer in answers if answer).strip()
    for url in extract_urls_from_text(final_answer):
        source = {"title": url, "link": url}
        if source not in used_sources:
            used_sources.append(source)
    return {
        "answer": final_answer or "I’m not sure.",
        "sources": used_sources[:3],
        "is_greeting": False,
        "is_summary": False,
        "chat_mode": CHAT_MODE_WEB_SEARCH,
        "resolved_query": resolved_queries[0] if resolved_queries else cleaned_query,
    }


def _select_llm(model_name: str):
    if model_name in GEMINI_LLM_MODELS:
        return GeminiClient().get_llm(model_name)
    return GroqClient().get_llm(model_name)


def _format_results(results: list[dict]) -> str:
    sections = []
    for index, result in enumerate(results, start=1):
        snippet = (result.get("snippet") or "")[:WEB_SEARCH_CONTENT_SNIPPET_LEN]
        sections.append(f"[{index}] {result.get('title', '')}\nURL: {result.get('link', '')}\n{snippet}")
    return "\n\n".join(sections)


def _parse_web_answer(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        return {"answer": "", "used_result_ids": []}

    payload = parse_json_dict(text)
    if isinstance(payload, dict):
        answer = str(payload.get("answer", "")).strip()
        used_result_ids = payload.get("used_result_ids", [])
        if not isinstance(used_result_ids, list):
            used_result_ids = []

        normalized_ids = []
        for item in used_result_ids:
            try:
                normalized_ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return {
            "answer": answer,
            "used_result_ids": normalized_ids,
        }

    return {"answer": extract_json_candidate(text) or text, "used_result_ids": []}


def _select_web_sources(results: list[dict], used_result_ids: list[int]) -> list[dict]:
    sources = []
    indexes = used_result_ids or [1]
    for result_index in indexes:
        position = result_index - 1
        if position < 0 or position >= len(results):
            continue
        result = results[position]
        link = result.get("link")
        if not link:
            continue
        source = {
            "title": result.get("title", ""),
            "link": link,
        }
        if source not in sources:
            sources.append(source)
    return sources


def _focus_context(state: dict) -> str:
    topic = (state or {}).get("active_topic", "") or "No active topic"
    entities = ", ".join((state or {}).get("active_entities", [])[:5])
    if entities:
        return f"Stay anchored to: {topic}. Important entities: {entities}."
    return f"Stay anchored to: {topic}."
