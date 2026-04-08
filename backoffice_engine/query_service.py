"""
query_service.py
────────────────
Deterministic query refactoring helpers.
"""

from __future__ import annotations

import re


_ABBREVIATIONS = {
    "ai": "artificial intelligence",
    "ml": "machine learning",
    "nlp": "natural language processing",
    "llm": "large language model",
    "rag": "retrieval augmented generation",
}

_GREETING_PATTERN = re.compile(
    r"^\s*(hi|hello|hey|good morning|good evening|good afternoon)([!.?,\s]+)?$",
    re.IGNORECASE,
)
_OFFENSIVE_PATTERN = re.compile(r"\b(fuck|shit|bitch|asshole|bastard|idiot|stupid)\b", re.IGNORECASE)
_EXACT_PATTERN = re.compile(r"\b(exact words?|exactly|word to word|word for word|verbatim|define exactly)\b", re.IGNORECASE)
_REFERENCE_PATTERN = re.compile(r"\b(it|this|that|its|they|them|these|those)\b", re.IGNORECASE)
_QUESTION_HINT_PATTERN = re.compile(r"\b(what|which|where|when|why|how|who|explain|tell|define|list|summarize|summary|compare)\b", re.IGNORECASE)
_LIST_PATTERN = re.compile(r"\b(list|name|all names|only list|only the names)\b", re.IGNORECASE)
_SUMMARY_PATTERN = re.compile(r"\b(summary|summarize|summarise|overview|give me summary|what is this file|what is this document)\b", re.IGNORECASE)
_NUMERIC_FILTER_PATTERN = re.compile(r"\b(greater than|less than|more than|below|above|between|at least|at most)\b", re.IGNORECASE)
_SHORT_FOLLOWUP_PATTERN = re.compile(r"^\s*(list them|name them|show them|by which player|which player)\s*[?.!]*\s*$", re.IGNORECASE)
_SHORT_CONTEXT_QUERY_PATTERN = re.compile(
    r"^\s*(?P<prefix>what is|what's|define|meaning of|explain|tell me about)\s+(?P<phrase>[A-Za-z][A-Za-z0-9\s/-]{0,40})\s*[?.!]*\s*$",
    re.IGNORECASE,
)


def is_greeting_query(query: str, chat_history: list | None = None) -> bool:
    return not chat_history and bool(_GREETING_PATTERN.match(query or ""))


def contains_offensive_language(query: str) -> bool:
    return bool(_OFFENSIVE_PATTERN.search(query or ""))


def strip_offensive_language(query: str) -> str:
    stripped = _OFFENSIVE_PATTERN.sub(" ", query or "")
    return re.sub(r"\s+", " ", stripped).strip(" ,.!?")


def should_refuse_for_abuse(query: str) -> bool:
    if not contains_offensive_language(query):
        return False
    sanitized = strip_offensive_language(query)
    return not sanitized or not _QUESTION_HINT_PATTERN.search(sanitized)


def is_exact_request(query: str) -> bool:
    return bool(_EXACT_PATTERN.search(query or ""))


def expand_abbreviations(query: str) -> str:
    expanded = query or ""
    for short, full in _ABBREVIATIONS.items():
        expanded = re.sub(rf"\b{re.escape(short)}\b", full, expanded, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", expanded).strip()


def resolve_vague_query(query: str, chat_history: list | None = None, active_topic: str = "", active_entities: list[str] | None = None) -> str:
    text = re.sub(r"\s+", " ", (query or "").strip())
    if not text:
        return ""

    if _SHORT_FOLLOWUP_PATTERN.match(text) and active_topic:
        lowered = text.lower()
        if "list" in lowered or "name" in lowered or "show" in lowered:
            return f"List {active_topic}"
        if "which player" in lowered:
            return f"Which player {active_topic}"

    if _should_anchor_short_context_query(text) and active_topic and "file" not in text.lower() and "document" not in text.lower():
        return f"{text} in the context of {active_topic}"

    if not _REFERENCE_PATTERN.search(text):
        return text

    replacement = active_topic or _extract_history_topic(chat_history) or "the previous topic"
    protected = re.sub(r"\b(this|that)\s+(file|document|doc|pdf|page|context)\b", _protect_reference_phrase, text, flags=re.IGNORECASE)
    resolved = _REFERENCE_PATTERN.sub(replacement, protected)
    resolved = resolved.replace("__TECHNOCHAT_THIS__", "this").replace("__TECHNOCHAT_THAT__", "that")
    replaced_reference = resolved != text

    entities = active_entities or _extract_history_entities(chat_history)
    if replaced_reference and entities and replacement not in resolved:
        resolved = f"{resolved} about {' '.join(entities[:3])}"

    return re.sub(r"\s+", " ", resolved).strip()


def split_multi_question(query: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (query or "").strip())
    if not cleaned:
        return []

    pieces = [piece.strip(" ?.") for piece in re.split(r"\?+", cleaned) if piece.strip(" ?.")]
    if len(pieces) > 1:
        return pieces

    entity_parts = _split_shared_entity_question(cleaned)
    if entity_parts:
        return entity_parts

    wh_split = _split_on_secondary_wh(cleaned)
    if wh_split:
        return wh_split

    if re.search(r"\b(lowest|highest|best|most|least)\b", cleaned, re.IGNORECASE) and re.search(r"\band\s+how\s+(much|many)\b", cleaned, re.IGNORECASE):
        return [cleaned]

    if re.search(r"\b(what|which|where|when|why|how|who)\b.*\band\b.*\b(what|which|where|when|why|how|who)\b", cleaned, re.IGNORECASE):
        return [part.strip(" ?.") for part in re.split(r"\band\b", cleaned, flags=re.IGNORECASE) if part.strip(" ?.")]

    return [cleaned]


def build_query_variations(query: str, chat_history: list | None = None, active_topic: str = "", active_entities: list[str] | None = None) -> list[str]:
    """
    Always return 2–3 compact retrieval queries.
    """
    original = re.sub(r"\s+", " ", (query or "").strip())
    if not original:
        return []

    resolved = resolve_vague_query(original, chat_history=chat_history, active_topic=active_topic, active_entities=active_entities)
    expanded = expand_abbreviations(resolved)
    concise = _expand_query_for_intent(expanded)

    variations = []
    for candidate in (original, expanded, concise):
        if candidate and candidate not in variations:
            variations.append(candidate)
        if len(variations) == 3:
            break
    return variations


def get_resolved_query_text(query: str, chat_history: list | None = None, active_topic: str = "", active_entities: list[str] | None = None) -> str:
    original = re.sub(r"\s+", " ", (query or "").strip())
    if not original:
        return ""
    resolved = resolve_vague_query(original, chat_history=chat_history, active_topic=active_topic, active_entities=active_entities)
    expanded = expand_abbreviations(resolved)
    normalized = _normalize_special_cases(expanded or original)
    if _looks_like_entity_name(normalized):
        return f"Tell me about {normalized}"
    return normalized


def should_generate_image(query: str) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False

    action = r"(generate|create|make|design|draw|illustrate|render|produce|edit)"
    target = r"(image|picture|photo|poster|banner|illustration|artwork|art|logo|avatar|wallpaper)"

    if re.search(rf"\b{action}\b.*\b{target}\b", text):
        return True
    if re.search(rf"\b{target}\b.*\b{action}\b", text):
        return True
    return text.startswith("/image ")


def is_summary_request(query: str) -> bool:
    return bool(_SUMMARY_PATTERN.search(query or ""))


def is_list_request(query: str) -> bool:
    return bool(_LIST_PATTERN.search(query or ""))


def is_numeric_filter_request(query: str) -> bool:
    return bool(_NUMERIC_FILTER_PATTERN.search(query or ""))


def should_include_history_in_answer(query: str) -> bool:
    text = query or ""
    return bool(_REFERENCE_PATTERN.search(text) or _should_anchor_short_context_query(text))


def _is_short_context_query(text: str) -> bool:
    match = _SHORT_CONTEXT_QUERY_PATTERN.match(text or "")
    if not match:
        return False
    phrase = match.group("phrase").strip()
    return 1 <= len(phrase.split()) <= 3


def _should_anchor_short_context_query(text: str) -> bool:
    match = _SHORT_CONTEXT_QUERY_PATTERN.match(text or "")
    if not match:
        return False

    phrase = match.group("phrase").strip()
    prefix = match.group("prefix").strip().lower()
    if not (1 <= len(phrase.split()) <= 3):
        return False

    if prefix == "tell me about" and _looks_like_entity_name(phrase):
        return False

    return True


def _expand_short_query(query: str) -> str:
    word_count = len((query or "").split())
    if word_count == 0:
        return ""
    if word_count <= 3:
        return f"{query} mentioned in the document"
    return query


def _expand_query_for_intent(query: str) -> str:
    normalized = _normalize_special_cases(query)
    if _looks_like_entity_name(normalized):
        return f"who is {normalized} mentioned in the document"
    if is_summary_request(query):
        return f"{normalized} complete overview all people names countries statistics mentioned in the document"
    if is_list_request(query):
        return f"{normalized} exact names only all matching items mentioned in the document"
    if is_numeric_filter_request(query):
        return f"{normalized} exact numeric values only exact matching names mentioned in the document"
    return _expand_short_query(normalized)


def _extract_history_topic(chat_history: list | None) -> str:
    if not chat_history:
        return ""
    for message in reversed(chat_history):
        question = getattr(message, "question", "") or ""
        if question:
            return expand_abbreviations(question)
    return ""


def _extract_history_entities(chat_history: list | None) -> list[str]:
    if not chat_history:
        return []
    for message in reversed(chat_history):
        question = getattr(message, "question", "") or ""
        if question:
            return re.findall(r"\b[A-Za-z][A-Za-z0-9+-]{2,}\b", question)
    return []


def _protect_reference_phrase(match: re.Match) -> str:
    word = match.group(1).lower()
    suffix = match.group(2)
    placeholder = "__TECHNOCHAT_THIS__" if word == "this" else "__TECHNOCHAT_THAT__"
    return f"{placeholder} {suffix}"


def _split_shared_entity_question(query: str) -> list[str]:
    lowered = query.lower()
    anchor_index = -1
    anchor_text = ""

    for candidate in (" of ", " by "):
        index = lowered.find(candidate)
        if index != -1:
            anchor_index = index
            anchor_text = candidate
            break

    if anchor_index == -1:
        return []

    prefix = query[:anchor_index + len(anchor_text)].strip()
    entity_text = query[anchor_index + len(anchor_text):].strip(" ?.")
    if not prefix or not entity_text:
        return []
    if not _QUESTION_HINT_PATTERN.search(prefix):
        return []

    entities = _split_entity_series(entity_text)
    if len(entities) < 2:
        return []

    parts = []
    for entity in entities:
        parts.append(f"{prefix} {entity}".strip())
    return parts


def _split_entity_series(entity_text: str) -> list[str]:
    normalized = re.sub(r"\s+(and|&)\s+", ", ", entity_text.strip(), flags=re.IGNORECASE)
    raw_parts = normalized.split(",")
    entities = []

    for raw_part in raw_parts:
        candidate = raw_part.strip(" .?")
        if not candidate:
            continue
        if not _looks_like_entity(candidate):
            return []
        if candidate not in entities:
            entities.append(candidate)

    return entities


def _looks_like_entity(text: str) -> bool:
    words = [word for word in text.split() if word]
    if not words or len(words) > 5:
        return False

    capitalized_words = 0
    for word in words:
        if re.match(r"^[A-Z][A-Za-z'.-]*$", word):
            capitalized_words += 1
            continue
        if re.match(r"^[A-Z]{2,}$", word):
            capitalized_words += 1
            continue
        if re.match(r"^[A-Z][a-z]+[0-9]*$", word):
            capitalized_words += 1
            continue
        return False

    return capitalized_words >= 1


def _split_on_secondary_wh(query: str) -> list[str]:
    pattern = re.search(r"\b(and)\s+(what|when|where|why|how|who|which)\b", query, re.IGNORECASE)
    if not pattern:
        return []

    first_part = query[:pattern.start()].strip(" ?.")
    second_part = query[pattern.start() + len(pattern.group(1)) + 1:].strip(" ?.")
    if not first_part or not second_part:
        return []
    if not _QUESTION_HINT_PATTERN.search(first_part):
        return []
    lowered_first = first_part.lower()
    lowered_second = second_part.lower()
    if any(term in lowered_first for term in ("highest", "lowest", "best", "most", "least")) and lowered_second in {"how much", "how many", "what value"}:
        return []

    parts = [first_part, second_part]
    cleaned_parts = []
    for part in parts:
        if part and part not in cleaned_parts:
            cleaned_parts.append(part)
    return cleaned_parts


def _normalize_special_cases(query: str) -> str:
    normalized = query or ""
    normalized = re.sub(
        r"\bgap between a world cup\b",
        "gap between Cricket World Cups",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _looks_like_entity_name(text: str) -> bool:
    cleaned = re.sub(r"[?!.]+", "", text or "").strip()
    words = [word for word in cleaned.split() if word]
    if len(words) < 2 or len(words) > 4:
        return False
    for word in words:
        if not re.match(r"^[A-Z][A-Za-z'.-]*$", word):
            return False
    return True
