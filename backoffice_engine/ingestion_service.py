"""
ingestion_service.py
────────────────────
Chunking, embedding, and Pinecone upsert pipeline.

Public API
──────────
    embed_file_and_upsert(file_object: File)
"""

from .models import File
from .choices import FileProcessingStatus
from .clients import PineconeClient, LangchainClient
from .document_reader import extract_file_text
from techno_chat.settings import (
    logger,
    PINECONE_EMBED_BATCH_SIZE,
)
from .helpers import is_network_error
from .helpers import normalize_file_type, sanitise_filename
from .constants import _LOCATION_FIELDS
from .exceptions import (
    NetworkConnectionError, VLMQuotaExceededError,
    VLMStandaloneImageError, VLMEmbeddedImageError,
    NoTextExtractedError, IngestionError
)


# ─────────────────────────────────────────────────────────────────────────────
# INGESTION PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def _build_location_summary(chunk_obj: dict) -> str:
    parts = []
    if chunk_obj.get("page_index") is not None:
        parts.append(f"page {chunk_obj['page_index']}")
    if chunk_obj.get("slide_index") is not None:
        parts.append(f"slide {chunk_obj['slide_index']}")
    if chunk_obj.get("sheet_name"):
        parts.append(f"sheet {chunk_obj['sheet_name']}")
    if chunk_obj.get("row_start") is not None:
        row_end = chunk_obj.get("row_end") or chunk_obj["row_start"]
        parts.append(f"rows {chunk_obj['row_start']}-{row_end}")
    if chunk_obj.get("line_start") is not None:
        line_end = chunk_obj.get("line_end") or chunk_obj["line_start"]
        parts.append(f"lines {chunk_obj['line_start']}-{line_end}")
    if chunk_obj.get("section_name"):
        parts.append(f"section {chunk_obj['section_name']}")
    return ", ".join(parts)


def _build_indexable_text(original_filename: str, file_type: str, chunk_obj: dict) -> str:
    lines = [f"File: {original_filename}", f"Type: {file_type}"]
    location_summary = _build_location_summary(chunk_obj)
    if location_summary:
        lines.append(f"Location: {location_summary}")
    lines.append(chunk_obj["text"])
    return "\n".join(lines).strip()

def embed_file_and_upsert(file_object: File):
    """
    Full ingestion:
      1. extract_file_text  → List[{text, page_index, slide_index, ...}]
      2. For each segment, split text into sub-chunks (LangchainClient)
         each sub-chunk inherits ALL location fields from its parent segment
      3. Embed in batches (dense + sparse)
      4. Upsert to Pinecone with id = {file_id}_{sanitised_filename}_{chunk_index}
    """
    pinecone_client  = PineconeClient()
    langchain_client = LangchainClient()

    file_path         = file_object.file.path
    original_filename = file_object.original_filename or file_object.file.name
    normalized_file_type = normalize_file_type(file_object.file_type or "", original_filename)
    sanitised         = sanitise_filename(original_filename)

    # Final vector ID prefix:  {file_id}_{sanitised_filename}
    id_prefix = f"{file_object.id}_{sanitised}"

    logger.info("════════════════════════════════════════════")
    logger.info("INGEST | START")
    logger.info("INGEST | file_id=%s | filename=%s", file_object.id, original_filename)
    logger.info("INGEST | file_path=%s", file_path)
    logger.info("INGEST | id_prefix=%s", id_prefix)
    logger.info("════════════════════════════════════════════")

    logger.info(
        "Processing | id=%s | filename=%s | id_prefix=%s",
        file_object.id, original_filename, id_prefix
    )

    # ── Step 1: extract — rich location-aware segments ─────────────────
    logger.info("INGEST | ── STEP 1: extract_file_text ──")
    try:
        segments = extract_file_text(file_path)
    except (NetworkConnectionError, VLMQuotaExceededError, VLMStandaloneImageError, VLMEmbeddedImageError):
        file_object.embedding_status = FileProcessingStatus.FAILED
        file_object.save(update_fields=["embedding_status"])
        raise
    except Exception as e:
        logger.error("INGEST | STEP 1 FAILED | unexpected error | %s", e)
        file_object.embedding_status = FileProcessingStatus.FAILED
        file_object.save(update_fields=["embedding_status"])
        if is_network_error(e):
            raise NetworkConnectionError(internal=f"Network during extraction. id={file_object.id} raw={e}")
        raise IngestionError(internal=f"Extraction failed. id={file_object.id} raw={e}")

    # ── Step 2: split each segment into sub-chunks ─────────────────────
    if not segments:
        logger.error("INGEST | STEP 1 FAILED | extract_file_text returned empty — no text found in file")
        file_object.embedding_status = FileProcessingStatus.FAILED
        file_object.save(update_fields=["embedding_status"])
        raise NoTextExtractedError()
    logger.info("INGEST | STEP 1 DONE | total_segments=%s", len(segments))

    for i, seg in enumerate(segments):
        page    = seg.get("page_index")
        slide   = seg.get("slide_index")
        sheet   = seg.get("sheet_name")
        text_len = len(seg.get("text", ""))
        preview  = seg.get("text", "")[:80].replace("\n", " ")
        logger.debug(
            "INGEST | segment[%s] page=%s slide=%s sheet=%s text_len=%s preview='%s'",
            i, page, slide, sheet, text_len, preview
        )
 
    # ── STEP 2: Split segments into chunks ───────────────────────────────────
    logger.info("INGEST | ── STEP 2: split segments into chunks ──")

    all_chunks = []
    # for segment in segments:
    #     parent_text = segment["text"]
    #     loc = {f: segment.get(f) for f in _LOCATION_FIELDS}
    #     sub_chunks = langchain_client.split_text(full_text=parent_text)
    #     for sub in sub_chunks:
    #         all_chunks.append({"text": sub, **loc})

    for seg_idx, segment in enumerate(segments):
        parent_text = segment["text"]
        loc = {f: segment.get(f) for f in _LOCATION_FIELDS}
 
        sub_chunks = langchain_client.split_text(full_text=parent_text)
 
        logger.debug(
            "INGEST | segment[%s] page=%s → %s sub-chunks",
            seg_idx, loc.get("page_index"), len(sub_chunks)
        )
 
        for sub in sub_chunks:
            chunk_payload = {"text": sub, **loc}
            chunk_payload["indexed_text"] = _build_indexable_text(
                original_filename=original_filename,
                file_type=normalized_file_type,
                chunk_obj=chunk_payload,
            )
            all_chunks.append(chunk_payload)

    if not all_chunks:
        logger.error("INGEST | STEP 2 FAILED | all_chunks is empty after splitting")
        file_object.embedding_status = FileProcessingStatus.FAILED
        file_object.save(update_fields=["embedding_status"])
        raise NoTextExtractedError()

    logger.info("INGEST | STEP 2 DONE | total_chunks=%s", len(all_chunks))
    logger.info(
        "Chunks ready | id=%s | total_chunks=%s",
        file_object.id, len(all_chunks)
    )

    # ── Step 3 & 4: embed + upsert in batches ──────────────────────────
    # try:
    #     batch_size = PINECONE_EMBED_BATCH_SIZE
    #     vectors    = []

    #     for batch_start in range(0, len(all_chunks), batch_size):
    #         batch = all_chunks[batch_start : batch_start + batch_size]

    #         texts             = [c["text"] for c in batch]
    #         dense_embeddings  = pinecone_client.dense_text_embeddings(inputs=texts)
    #         sparse_embeddings = pinecone_client.sparse_text_embeddings(inputs=texts)
    #         sample = sparse_embeddings.data[0]
    #         logger.debug("=== INGEST SPARSE DEBUG ===")
    #         logger.debug("type: %s", type(sample))
    #         logger.debug("str: %s", str(sample)[:500])
    #         logger.debug("===========================")

    #         for i, chunk_obj in enumerate(batch):
    #             global_idx = batch_start + i

    #             dense_values    = dense_embeddings.data[i].values
    #             sparse_data     = sparse_embeddings.data[i]
    #             sparse_indices  = sparse_data.get("sparse_indices") or []
    #             sparse_values_l = sparse_data.get("sparse_values")  or []

    #             if not sparse_indices or not sparse_values_l:
    #                 logger.warning("Skipping chunk %s — empty sparse vector", global_idx)
    #                 continue

    #             metadata = {
    #                 "user_id":           file_object.user.id,
    #                 "document_id":       file_object.id,
    #                 "original_filename": original_filename,
    #                 "file_type":         file_object.file_type or "",
    #                 "chunk_index":       global_idx,
    #                 "text":              chunk_obj["text"],
    #             }
    #             for field in _LOCATION_FIELDS:
    #                 val = chunk_obj.get(field)
    #                 if val is not None:
    #                     metadata[field] = val

    #             vectors.append({
    #                 "id": f"{id_prefix}_{global_idx}",
    #                 "values": dense_values,
    #                 "sparse_values": {
    #                     "indices": sparse_indices,
    #                     "values":  sparse_values_l,
    #                 },
    #                 "metadata": metadata,
    #             })

    #     pinecone_client.upsert_file_data(vectors=vectors)
    #     file_object.embedding_status = FileProcessingStatus.COMPLETED
    #     file_object.save(update_fields=["embedding_status"])
    #     logger.info(
    #         "Embedded | id=%s | filename=%s | vectors=%s",
    #         file_object.id, original_filename, len(vectors)
    #     )
    # except (NetworkConnectionError, IngestionError):
    #     file_object.embedding_status = FileProcessingStatus.FAILED
    #     file_object.save(update_fields=["embedding_status"])
    #     raise
    # except Exception as e:
    #     file_object.embedding_status = FileProcessingStatus.FAILED
    #     file_object.save(update_fields=["embedding_status"])
    #     if is_network_error(e):
    #         raise NetworkConnectionError(internal=f"Network during embed/upsert. id={file_object.id} raw={e}")
    #     raise IngestionError(internal=f"Embed/upsert failed. id={file_object.id} raw={e}")


# ── STEP 3 & 4: Embed + Upsert ───────────────────────────────────────────
    logger.info("INGEST | ── STEP 3+4: embed and upsert in batches ──")
    logger.info("INGEST | batch_size=%s | total_batches=%s",
        PINECONE_EMBED_BATCH_SIZE,
        (len(all_chunks) + PINECONE_EMBED_BATCH_SIZE - 1) // PINECONE_EMBED_BATCH_SIZE
    )
 
    try:
        vectors       = []
        skipped       = 0
        batch_size    = PINECONE_EMBED_BATCH_SIZE
 
        for batch_start in range(0, len(all_chunks), batch_size):
            batch      = all_chunks[batch_start : batch_start + batch_size]
            batch_num  = (batch_start // batch_size) + 1
            batch_end  = min(batch_start + batch_size, len(all_chunks))
 
            logger.info(
                "INGEST | BATCH %s | chunks[%s:%s] | size=%s",
                batch_num, batch_start, batch_end, len(batch)
            )
 
            texts = [c["indexed_text"] for c in batch]
 
            # Dense embedding
            logger.info("INGEST | BATCH %s | creating dense embeddings...", batch_num)
            dense_embeddings = pinecone_client.dense_text_embeddings(inputs=texts)
            logger.info("INGEST | BATCH %s | dense embeddings created | count=%s", batch_num, len(dense_embeddings.data))
 
            # Sparse embedding
            logger.info("INGEST | BATCH %s | creating sparse embeddings...", batch_num)
            sparse_embeddings = pinecone_client.sparse_text_embeddings(inputs=texts)
            logger.info("INGEST | BATCH %s | sparse embeddings created | count=%s", batch_num, len(sparse_embeddings.data))
 
            # Build vectors
            for i, chunk_obj in enumerate(batch):
                global_idx = batch_start + i
 
                dense_values = dense_embeddings.data[i].values
 
                sparse_data     = sparse_embeddings.data[i].to_dict()
                sparse_indices  = sparse_data.get("sparse_indices") or []
                sparse_values_l = sparse_data.get("sparse_values")  or []
 
                vector_id = f"{id_prefix}_{global_idx}"
 
                metadata = {
                    "user_id":           file_object.user.id,
                    "document_id":       file_object.id,
                    "original_filename": original_filename,
                    "file_type":         file_object.file_type or "",
                    "normalized_file_type": normalized_file_type,
                    "chunk_index":       global_idx,
                    "text":              chunk_obj["text"],
                    "indexed_text":      chunk_obj["indexed_text"],
                    "location_summary":  _build_location_summary(chunk_obj),
                }
                for field in _LOCATION_FIELDS:
                    val = chunk_obj.get(field)
                    if val is not None:
                        metadata[field] = val
 
                vector = {
                    "id":     vector_id,
                    "values": dense_values,
                    "metadata": metadata,
                }
                if sparse_indices and sparse_values_l:
                    vector["sparse_values"] = {
                        "indices": sparse_indices,
                        "values": sparse_values_l,
                    }
                else:
                    logger.info(
                        "INGEST | dense-only upsert for chunk[%s] | location=%s",
                        global_idx,
                        metadata["location_summary"] or "n/a",
                    )
                    skipped += 1

                vectors.append(vector)
 
                logger.debug(
                    "INGEST | vector built | id=%s | page=%s | dense_len=%s | sparse_indices=%s | text_preview='%s'",
                    vector_id,
                    chunk_obj.get("page_index"),
                    len(dense_values),
                    len(sparse_indices),
                    chunk_obj["text"][:60].replace("\n", " ")
                )
 
            logger.info(
                "INGEST | BATCH %s | vectors built so far=%s | skipped so far=%s",
                batch_num, len(vectors), skipped
            )
 
        logger.info("INGEST | ── STEP 4: upserting %s vectors to Pinecone ──", len(vectors))
        if skipped > 0:
            logger.warning("INGEST | dense-only chunks (empty sparse)=%s out of %s", skipped, len(all_chunks))
 
        pinecone_client.upsert_file_data(vectors=vectors)
 
        file_object.embedding_status = FileProcessingStatus.COMPLETED
        file_object.save(update_fields=["embedding_status"])
 
        logger.info("════════════════════════════════════════════")
        logger.info("INGEST | COMPLETE")
        logger.info("INGEST | file_id=%s | filename=%s", file_object.id, original_filename)
        logger.info("INGEST | total_segments=%s | total_chunks=%s | vectors_upserted=%s | dense_only=%s",
            len(segments), len(all_chunks), len(vectors), skipped
        )
        logger.info("════════════════════════════════════════════")
 
    except (NetworkConnectionError, IngestionError):
        file_object.embedding_status = FileProcessingStatus.FAILED
        file_object.save(update_fields=["embedding_status"])
        raise
    except Exception as e:
        logger.error("INGEST | STEP 3+4 FAILED | error=%s", e)
        file_object.embedding_status = FileProcessingStatus.FAILED
        file_object.save(update_fields=["embedding_status"])
        if is_network_error(e):
            raise NetworkConnectionError(internal=f"Network during embed/upsert. id={file_object.id} raw={e}")
        raise IngestionError(internal=f"Embed/upsert failed. id={file_object.id} raw={e}")
