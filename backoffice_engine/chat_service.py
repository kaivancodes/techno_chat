"""
chat_service.py
────────────────
Main RAG orchestration.
"""

import re

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .clients import GeminiClient, GroqClient
from .constants import (
    _LOCATION_FIELDS,
    DEFAULT_RAG_CHUNK_LIMIT,
    DEFAULT_RAG_TOKEN_BUDGET,
    SUMMARY,
    SUMMARY_RAG_CHUNK_LIMIT,
    SUMMARY_RAG_TOKEN_BUDGET,
    CHAT_HISTORY_COUNT,
)
from .prompts import SYSTEM_PROMPT
from .query_service import (
    build_query_variations,
    contains_offensive_language,
    get_resolved_query_text,
    is_exact_request,
    is_greeting_query,
    is_list_request,
    is_numeric_filter_request,
    is_summary_request,
    should_include_history_in_answer,
    should_refuse_for_abuse,
    split_multi_question,
    strip_offensive_language,
)
from .page_render_service import get_page_render
from .retrieval_service import retrieve_query_variations
from .response_parsing_service import extract_json_candidate, parse_json_dict
from .schemas import SourceEntry
from .structured_file_service import try_build_structured_answer
from techno_chat.settings import GEMINI_LLM_MODELS, RET_SUMMARY_TOP_K, RE_SUMMARY_TOP_N, logger


EMPTY_RAG_RESPONSE = "I couldn't find relevant information in the provided document."
GREETING_RESPONSE = "Hi! How can I help you today?"
RESPECTFUL_RESPONSE = "Please keep our conversation respectful and I will be happy to help you."


def _build_history(chat_history: list) -> list:
    history = []
    limited_history = chat_history[-CHAT_HISTORY_COUNT:]
    for msg in limited_history:
        history.append(HumanMessage(content=msg.question))
        history.append(AIMessage(content=msg.answer))
    return history


def _select_llm(model_name: str):
    return GeminiClient().get_llm(model_name) if model_name in GEMINI_LLM_MODELS else GroqClient().get_llm(model_name)


def _get_highlight(chunk: dict, query: str, answer: str = "") -> str:
    file_type = (chunk.get("normalized_file_type") or chunk.get("file_type") or "").lower()
    if file_type in {"pdf", "doc", "docx", "ppt", "pptx", "image", "png", "jpg", "jpeg", "webp", "svg", "csv", "excel", "xlsx", "xls"}:
        return ""

    text = chunk.get("text", "") or ""
    if not text:
        return ""

    answer_fragments = _extract_answer_fragments(answer)
    for fragment in answer_fragments:
        if len(fragment) < 4:
            continue
        lowered_fragment = fragment.lower()
        if lowered_fragment in text.lower():
            idx = text.lower().find(lowered_fragment)
            return text[max(0, idx - 80): idx + min(len(fragment) + 180, 320)]

    for word in query.lower().split():
        lowered = word.strip(".,?!")
        if lowered and lowered in text.lower():
            idx = text.lower().find(lowered)
            return text[max(0, idx - 100): idx + 200]
    return text[:300]


def _calculate_confidence(chunks: list) -> float:
    if not chunks:
        return 0.0
    total = sum(chunk.get("score", 0) for chunk in chunks)
    return round(min(total / len(chunks), 1.0), 2)


def _extract_source_image(chunk: dict) -> str:
    try:
        file_id = chunk.get("file_id")
        page_index = chunk.get("page_index")
        file_type = (chunk.get("normalized_file_type") or chunk.get("file_type") or "").lower()
        if not file_id or not page_index or file_type != "pdf":
            return ""
        if "[Image" not in (chunk.get("text") or ""):
            return ""
        return get_page_render(file_id=file_id, page_index=page_index, highlight_text="")
    except Exception:
        return ""


def _source_location_key(chunk: dict) -> tuple:
    return (
        chunk.get("file_id"),
        chunk.get("page_index"),
        chunk.get("slide_index"),
        chunk.get("sheet_name"),
        chunk.get("row_start"),
        chunk.get("section_name"),
        chunk.get("line_start"),
    )


def _parse_structured_answer(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        return {"answer": EMPTY_RAG_RESPONSE, "used_context_ids": []}

    payload = parse_json_dict(text)
    if isinstance(payload, dict):
        answer = str(payload.get("answer", "")).strip()
        used_context_ids = payload.get("used_context_ids", [])
        if not isinstance(used_context_ids, list):
            used_context_ids = []
        normalized_ids = []
        for item in used_context_ids:
            try:
                normalized_ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return {
            "answer": answer or EMPTY_RAG_RESPONSE,
            "used_context_ids": normalized_ids,
        }

    return {"answer": extract_json_candidate(text) or text, "used_context_ids": []}


def _extract_answer_fragments(answer: str) -> list[str]:
    if not answer:
        return []

    fragments = []
    for raw_line in answer.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+\.)\s*", "", raw_line).strip()
        if len(cleaned) < 3:
            continue
        if cleaned not in fragments:
            fragments.append(cleaned)
        if len(fragments) >= 10:
            break
    return fragments


def _extract_named_phrases(text: str) -> list[str]:
    phrases = re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text or "")
    unique_phrases = []
    for phrase in phrases:
        if phrase not in unique_phrases:
            unique_phrases.append(phrase)
    return unique_phrases


def _build_sources(chunks: list[dict], query: str, answer: str, max_sources: int) -> list[SourceEntry]:
    scored_chunks = []
    answer_terms = set((answer or "").lower().split())
    query_terms = set((query or "").lower().split())
    answer_fragments = _extract_answer_fragments(answer)
    answer_entities = _extract_named_phrases(answer)

    for chunk in chunks:
        text = (chunk.get("text", "") or "").lower()
        overlap = 0
        for fragment in answer_fragments:
            if fragment.lower() in text:
                overlap += 6
        for entity in answer_entities:
            if entity.lower() in text:
                overlap += 4
        for term in query_terms:
            if term and term in text:
                overlap += 2
        for term in answer_terms:
            if term and term in text:
                overlap += 1
        scored_chunks.append((overlap + chunk.get("score", 0), chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)

    sources = []
    seen = set()
    for _, chunk in scored_chunks:
        location_key = _source_location_key(chunk)
        if location_key in seen:
            continue
        seen.add(location_key)

        entry: SourceEntry = {
            "file_name": chunk["file_name"],
            "file_type": chunk["file_type"],
            "file_id": chunk.get("file_id"),
            "highlight_text": _get_highlight(chunk, query, answer),
        }
        for field in _LOCATION_FIELDS:
            value = chunk.get(field)
            if value is not None:
                entry[field] = value

        image_url = _extract_source_image(chunk)
        if image_url:
            entry["image_url"] = image_url

        sources.append(entry)
        if len(sources) >= max_sources:
            break
    return _merge_adjacent_sources(sources)


def _format_context(chunks: list[dict]) -> str:
    sections = []
    for index, chunk in enumerate(chunks, start=1):
        location_bits = []
        if chunk.get("page_index") is not None:
            location_bits.append(f"page {chunk['page_index']}")
        if chunk.get("slide_index") is not None:
            location_bits.append(f"slide {chunk['slide_index']}")
        if chunk.get("sheet_name"):
            location_bits.append(f"sheet {chunk['sheet_name']}")
        if chunk.get("row_start") is not None:
            row_end = chunk.get("row_end") or chunk["row_start"]
            location_bits.append(f"rows {chunk['row_start']}-{row_end}")
        if chunk.get("line_start") is not None:
            line_end = chunk.get("line_end") or chunk["line_start"]
            location_bits.append(f"lines {chunk['line_start']}-{line_end}")
        if chunk.get("section_name"):
            location_bits.append(f"section {chunk['section_name']}")

        heading = f"[{index}]"
        if location_bits:
            heading += " " + " | ".join(location_bits)
        sections.append(f"{heading}\n{chunk.get('text', '')}")
    return "\n\n".join(sections)


def _extract_exact_answer(chunks: list[dict]) -> str:
    if not chunks:
        return EMPTY_RAG_RESPONSE
    return chunks[0].get("text", "").strip() or EMPTY_RAG_RESPONSE


def _select_used_chunks(selected_chunks: list[dict], used_context_ids: list[int], query: str) -> list[dict]:
    if not selected_chunks:
        return []
    if not used_context_ids:
        if is_summary_request(query) or is_list_request(query) or is_numeric_filter_request(query):
            return selected_chunks
        return [selected_chunks[0]]

    used_chunks = []
    seen_positions = set()
    for context_id in used_context_ids:
        if context_id < 1 or context_id > len(selected_chunks):
            continue
        position = context_id - 1
        if position in seen_positions:
            continue
        seen_positions.add(position)
        used_chunks.append(selected_chunks[position])

    if used_chunks:
        return used_chunks
    return [selected_chunks[0]]


def _merge_adjacent_sources(sources: list[SourceEntry]) -> list[SourceEntry]:
    if not sources:
        return []

    merged_sources = []
    for source in sources:
        if not merged_sources:
            merged_sources.append(dict(source))
            continue

        previous = merged_sources[-1]
        same_document = (
            previous.get("file_id") == source.get("file_id")
            and previous.get("file_type") == source.get("file_type")
            and previous.get("file_name") == source.get("file_name")
        )
        can_merge_pages = (
            same_document
            and previous.get("page_index") is not None
            and source.get("page_index") is not None
            and previous.get("slide_index") is None
            and source.get("slide_index") is None
            and previous.get("sheet_name") is None
            and source.get("sheet_name") is None
            and previous.get("section_name") is None
            and source.get("section_name") is None
            and previous.get("page_end", previous.get("page_index")) + 1 >= source.get("page_index")
        )
        if can_merge_pages:
            previous["page_end"] = source.get("page_end", source.get("page_index"))
            continue

        merged_sources.append(dict(source))

    return merged_sources


def _combine_sources(primary_sources: list[SourceEntry], secondary_sources: list[SourceEntry]) -> list[SourceEntry]:
    combined = []
    seen = set()

    for source in list(primary_sources) + list(secondary_sources):
        location_key = (
            source.get("file_id"),
            source.get("file_type"),
            source.get("page_index"),
            source.get("page_end"),
            source.get("slide_index"),
            source.get("sheet_name"),
            source.get("row_start"),
            source.get("row_end"),
            source.get("line_start"),
            source.get("line_end"),
            source.get("section_name"),
        )
        if location_key in seen:
            continue
        seen.add(location_key)
        combined.append(source)

    return _merge_adjacent_sources(combined)


def _chunk_order_key(chunk: dict) -> tuple:
    return (
        chunk.get("file_id") or 0,
        chunk.get("page_index") or 0,
        chunk.get("slide_index") or 0,
        chunk.get("sheet_name") or "",
        chunk.get("row_start") or 0,
        chunk.get("line_start") or 0,
        chunk.get("section_name") or "",
        chunk.get("chunk_index") or 0,
    )


def _order_chunks_for_request(chunks: list[dict], query: str) -> list[dict]:
    if is_summary_request(query) or is_list_request(query):
        return sorted(chunks, key=_chunk_order_key)
    return chunks


def _request_type(query: str) -> str:
    if is_exact_request(query):
        return "exact"
    if is_summary_request(query):
        return "summary"
    if is_list_request(query):
        return "list"
    if is_numeric_filter_request(query):
        return "numeric_filter"
    return "default"


def _answer_rules(query: str) -> str:
    request_type = _request_type(query)
    if request_type == "summary":
        return "Summarize all major entities and facts in the context. Do not focus on one item if multiple items are present. Cover the full spread of the retrieved context."
    if request_type == "list":
        return "Return only the requested list items from the context. No descriptions. No categories not asked for. No emojis. Deduplicate exact repeats."
    if request_type == "numeric_filter":
        return "Compare the numeric values carefully and include only items that truly satisfy the condition. Do not include near matches or explanatory mistakes."
    if request_type == "exact":
        return "Return the exact wording from the best matching context."
    lowered_query = (query or "").lower()
    if any(phrase in lowered_query for phrase in ("tell me about", "who is", "who's", "describe ")):
        return (
            "Answer directly from context only. Give a short fresh-sounding paraphrase in 3 to 5 sentences. "
            "Do not copy the document wording unless the user explicitly asks for exact or verbatim text."
        )
    if any(phrase in lowered_query for phrase in ("full stat", "full stats", "complete stats", "all stats")):
        return "Answer directly from context only. Include every available stat for the requested player or item, but paraphrase instead of copying the document."
    return "Answer directly from context only."


def _source_limit(query: str, question_parts: list[str]) -> int:
    if is_summary_request(query):
        return 10
    if is_list_request(query) or is_numeric_filter_request(query) or len(question_parts) > 1:
        return 12
    return 4


def build_chat_prompt(query: str, file_ids: list, chat_history: list, model_name: str, conversation_state: dict | None = None) -> dict:
    logger.info("build_chat_prompt | query=%s model=%s file_ids=%s", query, model_name, file_ids)

    if should_refuse_for_abuse(query):
        return {
            "answer": RESPECTFUL_RESPONSE,
            "sources": [],
            "is_greeting": False,
            "is_summary": False,
            "confidence": 1.0,
            "resolved_query": "",
        }

    cleaned_query = strip_offensive_language(query) if contains_offensive_language(query) else query

    if is_greeting_query(cleaned_query, chat_history):
        return {
            "answer": GREETING_RESPONSE,
            "sources": [],
            "is_greeting": True,
            "is_summary": False,
            "confidence": 1.0,
            "resolved_query": cleaned_query,
        }

    is_summary = any(item in cleaned_query.lower() for item in SUMMARY)
    is_exact_mode = is_exact_request(cleaned_query)
    is_list_mode = is_list_request(cleaned_query)
    is_numeric_mode = is_numeric_filter_request(cleaned_query)
    wants_full_coverage = " all " in f" {cleaned_query.lower()} " or bool(re.search(r"\ball\s+\d+\b", cleaned_query, re.IGNORECASE))
    top_k = RET_SUMMARY_TOP_K if (is_summary or is_list_mode or is_numeric_mode or wants_full_coverage) else None
    top_n = RE_SUMMARY_TOP_N if (is_summary or is_list_mode or is_numeric_mode or wants_full_coverage) else None
    if is_summary:
        max_chunks = max(SUMMARY_RAG_CHUNK_LIMIT, 24)
        token_budget = max(SUMMARY_RAG_TOKEN_BUDGET, 12000)
        max_per_location = 4
        preserve_source_order = True
    elif is_list_mode:
        max_chunks = 36 if wants_full_coverage else 20
        token_budget = 12000 if wants_full_coverage else 8000
        max_per_location = 6
        preserve_source_order = True
    elif is_numeric_mode:
        max_chunks = 18
        token_budget = 6000
        max_per_location = 4
        preserve_source_order = False
    else:
        max_chunks = DEFAULT_RAG_CHUNK_LIMIT
        token_budget = DEFAULT_RAG_TOKEN_BUDGET
        max_per_location = 2
        preserve_source_order = False
    lc_history = _build_history(chat_history) if should_include_history_in_answer(cleaned_query) else []
    llm = _select_llm(model_name)
    state = conversation_state or {}
    question_parts = split_multi_question(cleaned_query)

    logger.info(
        "build_chat_prompt | question_parts=%s | summary=%s | exact=%s | list=%s | numeric=%s | full_coverage=%s | max_chunks=%s | token_budget=%s",
        question_parts,
        is_summary,
        is_exact_mode,
        is_list_mode,
        is_numeric_mode,
        wants_full_coverage,
        max_chunks,
        token_budget,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "Question: {input}\nRequest rules: {rules}\nContext:\n{context}\n\nReturn valid JSON only with this shape:\n{{\"answer\": \"final answer here\", \"used_context_ids\": [1, 2]}}\nRules for used_context_ids:\n- Include only the context numbers actually used.\n- If one context is enough, return one id only.\n- If no relevant context exists, answer exactly with the fallback string and return an empty list."),
    ])
    chain = prompt | llm

    all_answers = []
    used_chunks = []
    resolved_queries = []
    direct_sources = []

    for question_part in question_parts:
        resolved_question_part = get_resolved_query_text(
            question_part,
            chat_history=chat_history,
            active_topic=state.get("active_topic", ""),
            active_entities=state.get("active_entities", []),
        )
        resolved_queries.append(resolved_question_part)

        if not is_exact_mode:
            try:
                direct_answer = try_build_structured_answer(resolved_question_part or question_part, file_ids)
            except Exception as exc:
                logger.warning("build_chat_prompt | structured answer skipped | query=%s raw=%s", question_part, exc)
                direct_answer = None

            if direct_answer:
                logger.info(
                    "build_chat_prompt | structured answer hit | query=%s | sources=%s",
                    question_part,
                    len(direct_answer.get("sources", [])),
                )
                all_answers.append(direct_answer["answer"])
                for source in direct_answer.get("sources", []):
                    direct_sources.append(source)
                continue

        query_variations = build_query_variations(
            question_part,
            chat_history=chat_history,
            active_topic=state.get("active_topic", ""),
            active_entities=state.get("active_entities", []),
        )
        logger.info(
            "build_chat_prompt | structured answer miss | query=%s | resolved=%s | refactored_queries=%s",
            question_part,
            resolved_question_part,
            query_variations,
        )
        if not query_variations:
            continue

        selected_chunks = retrieve_query_variations(
            query_variations=query_variations,
            file_ids=file_ids,
            top_k=top_k,
            top_n=top_n,
            max_chunks=max_chunks,
            token_budget=token_budget,
            max_per_location=max_per_location,
            preserve_source_order=preserve_source_order,
        )
        selected_chunks = _order_chunks_for_request(selected_chunks, question_part)
        logger.info(
            "build_chat_prompt | retrieved_chunks=%s | query=%s",
            len(selected_chunks),
            question_part,
        )

        if not selected_chunks:
            logger.info("build_chat_prompt | no chunks found for query=%s", question_part)
            continue

        if is_exact_mode:
            all_answers.append(_extract_exact_answer(selected_chunks))
            used_chunks.append(selected_chunks[0])
            logger.info("build_chat_prompt | exact mode answer selected from first chunk | query=%s", question_part)
            continue

        response = chain.invoke({
            "input": question_part,
            "rules": _answer_rules(question_part),
            "context": _format_context(selected_chunks),
            "chat_history": lc_history,
        })
        raw_answer = response.content if hasattr(response, "content") else str(response)
        structured = _parse_structured_answer(raw_answer)
        answer = structured["answer"].strip()
        part_used_chunks = _select_used_chunks(selected_chunks, structured["used_context_ids"], question_part)
        used_chunks.extend(part_used_chunks)
        all_answers.append(answer)
        logger.info(
            "build_chat_prompt | llm answer built | query=%s | used_context_ids=%s | answer_len=%s",
            question_part,
            structured["used_context_ids"],
            len(answer),
        )

    if not used_chunks:
        if direct_sources and all_answers:
            final_answer = "\n\n".join(answer for answer in all_answers if answer).strip() or EMPTY_RAG_RESPONSE
            return {
                "answer": final_answer,
                "sources": _merge_adjacent_sources(direct_sources),
                "is_greeting": False,
                "is_summary": is_summary,
                "confidence": 1.0,
                "resolved_query": resolved_queries[0] if resolved_queries else cleaned_query,
            }
        return {
            "answer": EMPTY_RAG_RESPONSE,
            "sources": [],
            "is_greeting": False,
            "is_summary": is_summary,
            "confidence": 0.0,
            "resolved_query": resolved_queries[0] if resolved_queries else cleaned_query,
        }

    final_answer = "\n\n".join(answer for answer in all_answers if answer).strip() or EMPTY_RAG_RESPONSE
    logger.info(
        "build_chat_prompt | filtered_chunks=%s token_budget=%s final_len=%s direct_sources=%s",
        len(used_chunks),
        token_budget,
        len(final_answer),
        len(direct_sources),
    )
    return {
        "answer": final_answer,
        "sources": _combine_sources(
            direct_sources,
            _build_sources(
                used_chunks,
                cleaned_query,
                final_answer,
                _source_limit(cleaned_query, question_parts),
            ),
        ) if direct_sources else _build_sources(
            used_chunks,
            cleaned_query,
            final_answer,
            _source_limit(cleaned_query, question_parts),
        ),
        "is_greeting": False,
        "is_summary": is_summary,
        "confidence": 1.0 if direct_sources else _calculate_confidence(used_chunks),
        "resolved_query": resolved_queries[0] if resolved_queries else cleaned_query,
    }
