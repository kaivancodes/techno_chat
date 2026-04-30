"""
conversation_state_service.py
─────────────────────────────
Lightweight per-session state used to resolve follow-up queries across modes.
"""

from __future__ import annotations

import re
from collections import Counter


SESSION_KEY = "conversation_state"
LAST_CHAT_KEY = "last_chat_session_id"
_PERSONAL_MEMORY_LIMIT = 8
_NAME_MEMORY_PATTERN = re.compile(
    r"^\s*my name is\s+(?P<name>[A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*){0,4})\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_NAME_RECALL_PATTERN = re.compile(
    r"^\s*(?:what is my name|what's my name|tell me my name|who am i)\s*[?!.]*\s*$",
    re.IGNORECASE,
)
_TOPIC_RECALL_PATTERN = re.compile(
    r"^\s*(?:what(?:\s+are|'?re)?\s+we\s+talking\s+about|what\s+we\s+are\s+talking\s+about|what\s+is\s+the\s+(?:current\s+)?topic|which\s+topic\s+are\s+we\s+on)\s*[?!.]*\s*$",
    re.IGNORECASE,
)

_STOPWORDS = {
    "what", "which", "where", "when", "why", "how", "who", "is", "are", "the",
    "a", "an", "of", "to", "for", "and", "or", "in", "on", "with", "about",
    "tell", "me", "explain", "give", "show", "its", "it", "this", "that",
    "these", "those", "their", "them",
}
_TOPIC_HISTORY_LIMIT = 8
_ENTITY_HISTORY_LIMIT = 8
_CRICKET_TERMS = {
    "cricket", "odi", "batting", "bowling", "batsman", "batter", "bowler",
    "runs", "wickets", "strike", "rate", "economy", "average", "centuries",
    "fifties", "sixes", "fours", "catches", "stumpings", "runouts",
    "cricketer", "cricketers", "player", "players", "captain", "keeper",
    "wicketkeeper", "allrounder", "all-rounder", "innings", "overs",
}
_ENTITY_ONLY_QUERY_PATTERN = re.compile(
    r"^\s*(?:tell me about|who is|who's|describe|about)\s+[A-Z][A-Za-z'.-]*(?:\s+[A-Z][A-Za-z'.-]*){0,3}\s*[?.!]*\s*$"
)


def get_conversation_state(request, session_id: int) -> dict:
    all_state = request.session.get(SESSION_KEY, {})
    return _normalize_state(all_state.get(str(session_id), {}))


def update_conversation_state(request, session_id: int, query: str, resolved_query: str = "") -> dict:
    text = (resolved_query or query or "").strip()
    all_state = request.session.get(SESSION_KEY, {})
    current = _normalize_state(all_state.get(str(session_id), {}))

    if text and not (_is_entity_only_query(text) and current["recent_queries"]):
        current["recent_queries"].append(text)
        current["recent_queries"] = current["recent_queries"][-_TOPIC_HISTORY_LIMIT:]

    entities = _extract_entities(text)
    if entities:
        merged_entities = current["recent_entities"] + entities
        deduped_entities = []
        for item in merged_entities:
            if item.lower() not in [existing.lower() for existing in deduped_entities]:
                deduped_entities.append(item)
        current["recent_entities"] = deduped_entities[-_ENTITY_HISTORY_LIMIT:]

    topic = _derive_topic_from_history(current["recent_queries"])
    if topic:
        current["active_topic"] = topic

    if current["recent_entities"]:
        current["active_entities"] = current["recent_entities"][:5]

    memory_update = extract_personal_memory_update(text)
    if memory_update:
        memories = dict(current.get("personal_memory", {}))
        memories.update(memory_update)
        current["personal_memory"] = dict(list(memories.items())[-_PERSONAL_MEMORY_LIMIT:])

    all_state[str(session_id)] = current
    request.session[SESSION_KEY] = all_state
    request.session.modified = True
    return current


def set_last_active_chat_session(request, session_id: int) -> None:
    request.session[LAST_CHAT_KEY] = session_id
    request.session.modified = True


def get_last_active_chat_session_id(request) -> int | None:
    return request.session.get(LAST_CHAT_KEY)


def _normalize_state(state: dict | None) -> dict:
    current = dict(state or {})
    current.setdefault("active_topic", "")
    current.setdefault("active_entities", [])
    current.setdefault("recent_queries", [])
    current.setdefault("recent_entities", list(current.get("active_entities", [])))
    current.setdefault("personal_memory", {})
    return current


def extract_personal_memory_update(text: str) -> dict:
    match = _NAME_MEMORY_PATTERN.match(text or "")
    if not match:
        return {}
    name = re.sub(r"\s+", " ", match.group("name")).strip()
    if not name:
        return {}
    return {"name": name}


def answer_personal_memory_query(text: str, state: dict | None) -> str:
    if not _NAME_RECALL_PATTERN.match(text or ""):
        return ""
    memory = (state or {}).get("personal_memory", {})
    return str(memory.get("name", "")).strip()


def answer_conversation_focus_query(text: str, state: dict | None, has_document: bool = False) -> str:
    if not _TOPIC_RECALL_PATTERN.match(text or ""):
        return ""

    current_state = state or {}
    topic = str(current_state.get("active_topic", "")).strip()
    entities = [str(item).strip() for item in current_state.get("active_entities", []) if str(item).strip()]
    scope = "in the current document" if has_document else "in this conversation"

    if topic and entities:
        return f"We are talking about {topic} {scope}, especially {', '.join(entities[:3])}."
    if topic:
        return f"We are talking about {topic} {scope}."
    if entities:
        return f"We are talking about {', '.join(entities[:3])} {scope}."
    return ""


def _extract_topic(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", " ", text or "")
    words = [word for word in cleaned.split() if word.lower() not in _STOPWORDS]
    if not words:
        return ""
    return " ".join(words[:6])


def _extract_entities(text: str) -> list[str]:
    phrases = re.findall(r"\b[A-Z][A-Za-z'.-]*(?:\s+[A-Z][A-Za-z'.-]*){0,3}\b", text or "")
    entities = []
    for token in phrases:
        cleaned = token.strip()
        lowered = cleaned.lower()
        if lowered in _STOPWORDS:
            continue
        if lowered not in [item.lower() for item in entities]:
            entities.append(cleaned)
    return entities


def _derive_topic_from_history(recent_queries: list[str]) -> str:
    queries = [item for item in recent_queries if item]
    if not queries:
        return ""

    token_counter = Counter()
    for query in queries:
        cleaned = re.sub(r"[^a-zA-Z0-9\s-]", " ", query.lower())
        for token in cleaned.split():
            if token in _STOPWORDS or len(token) < 3:
                continue
            token_counter[token] += 1

    if _is_cricket_topic(token_counter):
        return "cricket statistics and player performance"

    repeated_terms = [token for token, count in token_counter.most_common() if count >= 2]
    if repeated_terms:
        return " ".join(repeated_terms[:5])

    for query in reversed(queries):
        topic = _extract_topic(query)
        if topic:
            return topic
    return ""


def _is_cricket_topic(token_counter: Counter) -> bool:
    cricket_hits = [token for token in token_counter if token in _CRICKET_TERMS]
    return len(cricket_hits) >= 2


def _is_entity_only_query(text: str) -> bool:
    return bool(_ENTITY_ONLY_QUERY_PATTERN.match(text or ""))
