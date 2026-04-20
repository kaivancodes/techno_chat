"""
retrieval_service.py
────────────────────
Hybrid vector similarity search + reranking.
"""

from .clients import PineconeClient
from .models import File
from .query_service import build_query_variations, get_resolved_query_text
from techno_chat.settings import (
    logger,
    RETRIEVAL_TOP_K,
    RERANK_TOP_N,
)
from .constants import _LOCATION_FIELDS


# ─────────────────────────────────────────────────────────────
# LOCAL SCORING
# ─────────────────────────────────────────────────────────────

def _keyword_score(text: str, query_texts: list[str]) -> int:
    score = 0
    text_lower = text.lower()
    for query in query_texts:
        lowered_query = (query or "").strip().lower()
        if not lowered_query:
            continue
        if lowered_query in text_lower:
            score += 8
        seen_terms = set()
        for word in lowered_query.split():
            token = word.strip(".,?!:;()[]{}\"'`")
            if len(token) < 2 or token in seen_terms:
                continue
            seen_terms.add(token)
            if token in text_lower:
                score += 1
    return score


def _local_rerank(results: list, query_texts: list[str], top_n: int):
    scored = []

    for r in results:
        semantic = r.get("score", 0)
        keyword = _keyword_score(r.get("text", ""), query_texts)

        final_score = semantic + (0.35 * keyword)
        scored.append((final_score, r))

    scored.sort(reverse=True, key=lambda x: x[0])

    return [r for _, r in scored[:top_n]]


def _chunk_identity(chunk: dict) -> tuple:
    return (
        chunk.get("file_id"),
        chunk.get("chunk_index"),
        chunk.get("page_index"),
        chunk.get("slide_index"),
        chunk.get("sheet_name"),
        chunk.get("row_start"),
        chunk.get("line_start"),
        chunk.get("section_name"),
    )


def _estimate_tokens(text: str) -> int:
    return max(1, int(len((text or "").split()) * 0.8))


def _chunk_location_key(chunk: dict) -> tuple:
    return (
        chunk.get("file_id"),
        chunk.get("page_index"),
        chunk.get("slide_index"),
        chunk.get("sheet_name"),
        chunk.get("row_start"),
        chunk.get("section_name"),
    )


def _chunk_sort_key(chunk: dict) -> tuple:
    file_id = chunk.get("file_id") or 0
    page_index = chunk.get("page_index") or 0
    slide_index = chunk.get("slide_index") or 0
    sheet_name = chunk.get("sheet_name") or ""
    row_start = chunk.get("row_start") or 0
    line_start = chunk.get("line_start") or 0
    section_name = chunk.get("section_name") or ""
    chunk_index = chunk.get("chunk_index") or 0
    return (file_id, page_index, slide_index, sheet_name, row_start, line_start, section_name, chunk_index)


def filter_retrieved_chunks(
    original_query: str,
    query_texts: list[str],
    results: list[dict],
    max_chunks: int,
    token_budget: int,
    max_per_location: int = 1,
    preserve_source_order: bool = False,
) -> list[dict]:
    ranked = _local_rerank(results, query_texts or [original_query], max(len(results), max_chunks))
    selected = []
    seen = set()
    location_counts = {}
    used_tokens = 0

    for allow_repeat_locations in (False, True):
        for chunk in ranked:
            identity = _chunk_identity(chunk)
            if identity in seen:
                continue

            location_key = _chunk_location_key(chunk)
            keyword_hits = _keyword_score(chunk.get("text", ""), query_texts or [original_query])
            semantic_score = chunk.get("score", 0)
            estimated_tokens = _estimate_tokens(chunk.get("text", ""))

            if keyword_hits == 0 and semantic_score <= 0.05 and selected:
                continue
            if not allow_repeat_locations and location_counts.get(location_key, 0) >= max_per_location:
                continue
            if len(selected) >= max_chunks:
                break
            if used_tokens + estimated_tokens > token_budget and selected:
                continue

            selected.append(chunk)
            seen.add(identity)
            location_counts[location_key] = location_counts.get(location_key, 0) + 1
            used_tokens += estimated_tokens

        if len(selected) >= max_chunks:
            break

    if preserve_source_order:
        selected.sort(key=_chunk_sort_key)

    logger.info(
        "filter_retrieved_chunks | query=%s retrieved=%s filtered=%s tokens=%s",
        original_query,
        len(results),
        len(selected),
        used_tokens,
    )
    return selected


def retrieve_query_variations(
    query_variations: list[str],
    file_ids: list,
    top_k: int = None,
    top_n: int = None,
    max_chunks: int = 5,
    token_budget: int = 1600,
    max_per_location: int = 1,
    preserve_source_order: bool = False,
) -> list[dict]:
    merged_queries = [item for item in query_variations if item]
    primary_query = _select_primary_retrieval_query(merged_queries)
    effective_top_k = top_k or max(RETRIEVAL_TOP_K, min(max(max_chunks + 4, 10), 24))
    effective_top_n = top_n or max(RERANK_TOP_N, min(max(max_chunks, 8), 16))

    logger.info(
        "retrieve_query_variations | primary_query=%s variations=%s top_k=%s top_n=%s",
        primary_query,
        merged_queries,
        effective_top_k,
        effective_top_n,
    )

    merged_results = hybrid_search(
        query=primary_query,
        file_ids=file_ids,
        top_k=effective_top_k,
        top_n=effective_top_n,
    )
    logger.info(
        "retrieve_query_variations | variations=%s merged=%s",
        merged_queries,
        len(merged_results),
    )
    return filter_retrieved_chunks(
        original_query=merged_queries[0] if merged_queries else "",
        query_texts=merged_queries,
        results=merged_results,
        max_chunks=max_chunks,
        token_budget=token_budget,
        max_per_location=max_per_location,
        preserve_source_order=preserve_source_order,
    )


def _select_primary_retrieval_query(query_variations: list[str]) -> str:
    if not query_variations:
        return ""
    longest = max(query_variations, key=lambda item: len((item or "").strip()))
    return longest.strip()


def _context_location_label(chunk: dict) -> str:
    if chunk.get("page_index") is not None:
        return f"Page {chunk['page_index']}"
    if chunk.get("slide_index") is not None:
        return f"Slide {chunk['slide_index']}"
    if chunk.get("sheet_name"):
        if chunk.get("row_start") is not None:
            row_end = chunk.get("row_end") or chunk["row_start"]
            return f"{chunk['sheet_name']} rows {chunk['row_start']}-{row_end}"
        return chunk["sheet_name"]
    if chunk.get("section_name"):
        return chunk["section_name"]
    if chunk.get("line_start") is not None:
        line_end = chunk.get("line_end") or chunk["line_start"]
        return f"Lines {chunk['line_start']}-{line_end}"
    return ""


def build_document_context_text(
    query: str,
    file_ids: list | None,
    chat_history: list | None = None,
    conversation_state: dict | None = None,
    max_chunks: int = 4,
    token_budget: int = 1400,
) -> str:
    if not file_ids:
        return ""

    state = conversation_state or {}
    resolved_query = get_resolved_query_text(
        query,
        chat_history=chat_history or [],
        active_topic=state.get("active_topic", ""),
        active_entities=state.get("active_entities", []),
    )
    query_variations = build_query_variations(
        query,
        chat_history=chat_history or [],
        active_topic=state.get("active_topic", ""),
        active_entities=state.get("active_entities", []),
    )
    if not query_variations:
        query_variations = [resolved_query or query]

    chunks = retrieve_query_variations(
        query_variations=query_variations,
        file_ids=file_ids,
        max_chunks=max_chunks,
        token_budget=token_budget,
        max_per_location=2,
        preserve_source_order=True,
    )
    if not chunks:
        return ""

    sections = []
    for chunk in chunks:
        location_label = _context_location_label(chunk)
        prefix = f"{chunk.get('file_name', '')} · {location_label}" if location_label else chunk.get("file_name", "")
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        sections.append(f"{prefix}\n{text[:320]}".strip())

    return "\n\n".join(sections[:max_chunks])


# ─────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────

def hybrid_search(query: str, file_ids: list, top_k: int = None, top_n: int = None) -> list:

    if top_k is None:
        top_k = RETRIEVAL_TOP_K

    if top_n is None:
        top_n = RERANK_TOP_N

    client = PineconeClient()

    logger.info("━━━━ HYBRID SEARCH START ━━━━")
    logger.info("HS | input_query='%s'", query)
    logger.info("HS | file_ids=%s | top_k=%s | top_n=%s", file_ids, top_k, top_n)

    # ── File metadata mapping ──
    file_meta = {}
    if file_ids:
        for f in File.objects.filter(id__in=file_ids).values("id", "original_filename", "file_type"):
            file_meta[f["id"]] = {
                "file_name": f["original_filename"] or str(f["id"]),
                "file_type": f["file_type"] or "",
            }
    logger.info("HS | file_meta=%s", file_meta)

    # ── Embeddings ──
    logger.info("HS | creating dense embedding for query...")
    dense_emb = client.dense_text_embeddings(inputs=[query])
    logger.info("HS | dense embedding created | vector_len=%s", len(dense_emb.data[0].values))

    logger.info("HS | creating sparse embedding for query...")
    sparse_emb = client.sparse_text_embeddings(inputs=[query])

    dense_values = dense_emb.data[0].values
    sparse_data = sparse_emb.data[0]
    sparse_payload = sparse_data.to_dict() if hasattr(sparse_data, "to_dict") else sparse_data

    sparse_indices = sparse_payload.get("sparse_indices", [])
    sparse_values = sparse_payload.get("sparse_values", [])
    logger.info("HS | sparse embedding created | indices_count=%s", len(sparse_indices))

    # ── Metadata filter ──
    filters = None
    if file_ids:
        filters = {"document_id": {"$in": [int(fid) for fid in file_ids]}}
        logger.info("HS | pinecone filter=%s", filters)

    # ── Pinecone query ──
    logger.info("HS | sending hybrid query to Pinecone...")
    response = client.query_file_hybrid(
        dense_vectors=dense_values,
        sparse_indices=sparse_indices,
        sparse_values=sparse_values,
        top_k=top_k,
        filters=filters,
    )

    raw_matches = response.get("matches", [])
    logger.info("HS | pinecone returned %s raw matches", len(raw_matches))
 
    if not raw_matches:
        logger.warning("HS | NO MATCHES RETURNED FROM PINECONE — check namespace, filter, and index")
        return []
 

    results = []
    #for match in response.get("matches", []):
    for i, match in enumerate(raw_matches):
        metadata = match.get("metadata", {})
        fid = metadata.get("document_id")
        meta = file_meta.get(int(fid), {}) if fid else {}
        score = match.get("score", 0)
        text_preview = metadata.get("text", "")[:80].replace("\n", " ")
 
        logger.debug(
            "HS | match[%s] score=%.4f | file_id=%s | page=%s | chunk=%s | text_preview='%s'",
            i, score, fid,
            metadata.get("page_index"),
            metadata.get("chunk_index"),
            text_preview
        )

        result = {
            "text": metadata.get("text", ""),
            "score": match.get("score", 0),
            "file_id": metadata.get("document_id"),
            "chunk_index": metadata.get("chunk_index"),
            "file_name": meta.get("file_name", metadata.get("original_filename", "")),
            "file_type": meta.get("file_type", metadata.get("file_type", "")),
            "normalized_file_type": metadata.get("normalized_file_type", ""),
        }

        for field in _LOCATION_FIELDS:
            result[field] = metadata.get(field)

        results.append(result)

    logger.info("hybrid_search | query_len=%s file_ids=%s results=%s",
                len(query), file_ids, len(results))

    # ── Pinecone rerank ──
    if len(results) > 1:
        try:
            docs = [r["text"] for r in results]
            logger.info("HS | sending %s docs to Pinecone reranker...", len(docs))

            rerank_resp = client.rerank_documents(
                query=query,
                documents=docs,
                top_n=min(top_n, len(docs))
            )

            reranked = []
            for item in rerank_resp.data:
                reranked.append(results[item.index])
            logger.info("HS | pinecone reranked | top result score=%.4f | text_preview='%s'",
                reranked[0].get("score", 0),
                reranked[0].get("text", "")[:80].replace("\n", " ")
            )

            results = reranked
            logger.info("HS | using Pinecone reranked results — skipping local rerank")
            logger.info("━━━━ HYBRID SEARCH END | returning %s results ━━━━", len(results))
            logger.info("hybrid_search | pinecone reranked to %s", len(results))

        except Exception as e:
            logger.warning("Pinecone rerank failed, using local rerank: %s", e)

            # ── Local rerank fallback only ──
            logger.info("HS | applying local rerank as fallback...")
            results = _local_rerank(results, query, top_n)
            logger.info("HS | local reranked | top result text_preview='%s'",
                results[0].get("text", "")[:80].replace("\n", " ") if results else "EMPTY"
            )
            logger.info("━━━━ HYBRID SEARCH END | returning %s results ━━━━", len(results))
    return results
