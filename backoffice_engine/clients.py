from typing import List, Any

import base64
import time

from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone
from langchain_core.utils.utils import convert_to_secret_str
import requests as _requests
from techno_chat.settings import (
    # Pinecone
    PINECONE_API_KEY,
    PINECONE_HOST_URL,
    PINECONE_DENSE_EMBEDDING_MODEL,
    PINECONE_SPARSE_EMBEDDING_MODEL,
    PINECONE_RERANK_MODEL,
    PINECONE_UPSERT_BATCH_SIZE,
    PINECONE_NAMESPACE,
    RETRIEVAL_TOP_K,
    RERANK_TOP_N,
    # Langchain
    TEXT_SPLITTER_CHUNK_SIZE,
    TEXT_SPLITTER_CHUNK_OVERLAP_SIZE,
    # Groq
    GROQ_API_KEY,
    GROQ_CHAT_COMPLETION_TEMPERATURE,
    GROQ_LLM_MODELS,
    # Gemini
    GOOGLE_API_KEY,
    GOOGLE_CHAT_COMPLETION_TEMPERATURE,
    GEMINI_LLM_MODELS,
    VLM_MODEL,
    KIE_API_KEY,
    OPENAI_IMAGE_MODEL,
    OPENAI_TEXT_IMAGE_MODEL,
    SERPER_API_KEY,
    SERPER_ENDPOINT,
    SERPER_MAX_RESULTS,
    # Logger
    logger,
)
from backoffice_engine.exceptions import WebSearchError
from .helpers import normalise_image, retry_on_network


class PineconeClient:
    def __init__(self, api_key: str = PINECONE_API_KEY, host_url: str = PINECONE_HOST_URL):
        """
        Initializes Pinecone client and index connection.
        """
        self.client = Pinecone(api_key=api_key)
        self.index = self.client.Index(host=host_url)
        logger.info("Pinecone Client Initialized Successfully")

    @retry_on_network()
    def dense_text_embeddings(self, inputs) -> Any:
        """
        Generate dense embeddings for text inputs.
        """
        dense_embeddings = self.client.inference.embed(
            model=PINECONE_DENSE_EMBEDDING_MODEL,
            inputs=inputs,
            parameters={
                "input_type": "passage",
                "truncate": "END",
            },
        )
        logger.info("Dense Embedding Created Successfully")
        return dense_embeddings

    @retry_on_network()
    def sparse_text_embeddings(self, inputs) -> Any:
        """
        Generate sparse embeddings for text inputs.
        """
        sparse_embeddings = self.client.inference.embed(
            model=PINECONE_SPARSE_EMBEDDING_MODEL,
            inputs=inputs,
            parameters={
                "input_type": "passage",
                "truncate": "END",
            },
        )
        logger.info("Sparse Embedding Created Successfully")
        return sparse_embeddings

    @retry_on_network()
    def upsert_file_data(self, vectors, batch_size: int = PINECONE_UPSERT_BATCH_SIZE):
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            self.index.upsert(vectors=batch, namespace=PINECONE_NAMESPACE)
        logger.info("Vector Data Inserted Successfully")
        return True

    @retry_on_network()
    def query_file_hybrid(self, dense_vectors: list, sparse_indices: list, sparse_values: list, top_k: int = RETRIEVAL_TOP_K, include_metadata: bool = True, filters=None):
        """
        Perform a hybrid (dense + sparse) query on the Pinecone index
        with optional metadata filtering.
        """
        sparse_indices = sparse_indices or []
        sparse_values = sparse_values or []

        query_response = self.index.query(
            top_k=top_k,
            vector=dense_vectors,
            sparse_vector={
                "indices": sparse_indices,
                "values": sparse_values,
            },
            filter=filters,
            include_metadata=include_metadata,
            namespace=PINECONE_NAMESPACE,
        )
        logger.info("Fetched Response Using Hybrid Query Successfully")
        return query_response

    @retry_on_network()
    def rerank_documents(self, query: str, documents: List[str], top_n: int = RERANK_TOP_N, return_documents: bool = True):
        """
        Rerank retrieved documents using a cross-encoder reranking model.
        """
        rerank_response = self.client.inference.rerank(
            model=PINECONE_RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=return_documents,
        )
        logger.info("Reranked Documents Successfully")
        return rerank_response


class LangchainClient:
    def __init__(self):
        logger.info("Langchain Client Initialized Successfully")

    def split_text(self, full_text: str, chunk_size=TEXT_SPLITTER_CHUNK_SIZE, overlap_size=TEXT_SPLITTER_CHUNK_OVERLAP_SIZE):
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap_size
        )
        chunks = splitter.split_text(full_text)
        logger.info("Text Successfully Split Into Chunks")
        return chunks


class GroqClient:
    def __init__(self, api_key: str = GROQ_API_KEY):
        self.api_key = api_key
        logger.info("Groq Client Initialized Successfully")

    def get_llm(self, llm_model: str) -> ChatGroq:
        model_id = GROQ_LLM_MODELS.get(llm_model)
        if not model_id:
            raise ValueError(f"Unknown Groq model '{llm_model}'. Available: {list(GROQ_LLM_MODELS.keys())}")
        return ChatGroq(api_key=convert_to_secret_str(self.api_key), model=model_id, temperature=GROQ_CHAT_COMPLETION_TEMPERATURE)

    def chat(self, user_prompt=None, system_prompt=None, llm_model=None) -> str:
        messages = []
        if system_prompt: messages.append(("system", system_prompt))
        if user_prompt:   messages.append(("human", user_prompt))
        response = self.get_llm(llm_model).invoke(messages)
        logger.info("Groq Response Received Successfully")
        return response.content

class GeminiClient:
    def __init__(self, api_key: str = GOOGLE_API_KEY):
        self.api_key = api_key
        logger.info("Gemini Client Initialized Successfully")

    def get_llm(self, llm_model: str) -> ChatGoogleGenerativeAI:
        model_id = GEMINI_LLM_MODELS.get(llm_model)
        if not model_id:
            raise ValueError(f"Unknown Gemini model '{llm_model}'. Available: {list(GEMINI_LLM_MODELS.keys())}")
        return ChatGoogleGenerativeAI(google_api_key=self.api_key, model=model_id, top_p=0.8,
                                      temperature=GOOGLE_CHAT_COMPLETION_TEMPERATURE)

    def chat(self, user_prompt=None, system_prompt=None, llm_model=None) -> str:
        messages = []
        if system_prompt: messages.append(("system", system_prompt))
        if user_prompt:   messages.append(("human", user_prompt))
        response = self.get_llm(llm_model).invoke(messages)
        logger.info("Gemini Response Received Successfully")
        return response.content


class VLMClient:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            google_api_key=GOOGLE_API_KEY,
            model=VLM_MODEL,
            temperature=0,
        )

    def describe_image_bytes(self, image_bytes: bytes, ext: str) -> str:
        image_bytes, ext = normalise_image(image_bytes, ext)
        b64      = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/{ext};base64,{b64}"

        prompt = (
            "You are an OCR and image-captioning assistant.\n"
            "1. Write a concise factual caption.\n"
            "2. List visible objects and their attributes.\n"
            "3. Transcribe ALL readable text exactly as it appears.\n"
            "Output format:\n- Caption:\n- Objects:\n- Visible Text:"
        )
        response = self.llm.invoke([{
            "role": "user",
            "content": [
                {"type": "text",      "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }])
        return response.content.strip()

    @retry_on_network()
    def describe_image_file(self, file_path: str) -> str:
        ext = file_path.rsplit(".", 1)[-1].lower()
        with open(file_path, "rb") as fh:
            return self.describe_image_bytes(fh.read(), ext)

    @retry_on_network()
    def describe_svg_file(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8") as fh:
            svg_content = fh.read()

        prompt = (
            "You are given raw SVG XML.\n"
            "1. Extract all visible text elements.\n"
            "2. Briefly describe what it visually represents.\n"
            "Do NOT explain XML structure.\n\n"
            f"SVG:\n{svg_content}"
        )
        return self.llm.invoke([("human", prompt)]).content.strip()

class SerperClient:
    """
    HTTP client for Serper.dev Google Search API.
    POST https://google.serper.dev/search
    """
    def __init__(self):
        self._api_key   = SERPER_API_KEY
        self._endpoint  = SERPER_ENDPOINT
        self._max_results = SERPER_MAX_RESULTS
        logger.info('SerperClient Initialized Successfully')

    def search(self, query: str) -> list[dict]:
        """
        Call Serper.dev and return a list of result dicts.
        Each dict has: title (str), link (str), snippet (str).
        Raises WebSearchError on HTTP error or unexpected response.
        """
        try:
            payload  = {'q': query, 'num': self._max_results}
            headers  = {'X-API-KEY': self._api_key, 'Content-Type': 'application/json'}
            response = _requests.post(
                self._endpoint, json=payload, headers=headers, timeout=10
            )
            response.raise_for_status()
            data    = response.json()
            results = []
            for item in data.get('organic', [])[:self._max_results]:
                results.append({
                    'title':   item.get('title',   ''),
                    'link':    item.get('link',    ''),
                    'snippet': item.get('snippet', ''),
                })
            if not results:
                # try answerBox or knowledgeGraph as fallback
                box = data.get('answerBox', {})
                if box.get('answer') or box.get('snippet'):
                    results.append({
                        'title':   box.get('title', 'Answer'),
                        'link':    box.get('link', ''),
                        'snippet': box.get('answer') or box.get('snippet', ''),
                    })
            logger.info('SerperClient search | query=%s results=%s', query[:50], len(results))
            return results
        except _requests.exceptions.RequestException as exc:
            raise WebSearchError(internal=f'Serper.dev request failed: {exc}')
        except Exception as exc:
            raise WebSearchError(internal=f'Serper.dev unexpected error: {exc}')


class KieImageClient:
    base_url = "https://api.kie.ai/api/v1"
    upload_base_url = "https://kieai.redpandaai.co"

    def __init__(self, api_key: str = KIE_API_KEY):
        self.api_key = api_key
        self.text_model = OPENAI_IMAGE_MODEL or OPENAI_TEXT_IMAGE_MODEL
        self.edit_model = OPENAI_IMAGE_MODEL or OPENAI_TEXT_IMAGE_MODEL
        logger.info("KieImageClient Initialized Successfully")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _normalise_image_inputs(self, image_inputs: list[str]) -> list[str]:
        unique_inputs = []
        for item in image_inputs:
            if not item:
                continue
            if item not in unique_inputs:
                unique_inputs.append(item)
        return unique_inputs

    def _uses_4o_endpoint(self, model: str) -> bool:
        lowered = (model or "").lower()
        return lowered == "4o-image-api" or "4o-image" in lowered

    @retry_on_network()
    def _upload_data_url(self, data_url: str, file_name: str = "input-image.png") -> str:
        response = _requests.post(
            f"{self.upload_base_url}/api/file-base64-upload",
            json={
                "base64Data": data_url,
                "uploadPath": "images",
                "fileName": file_name,
            },
            headers=self._headers(),
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        file_url = self._extract_upload_url(payload)
        if not file_url:
            logger.error("KIE upload response missing file URL | payload_keys=%s", list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__)
            raise ValueError("KIE image upload failed.")
        return file_url

    def _extract_upload_url(self, payload: dict | str | list | None) -> str:
        def _pull_url(value):
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
            if isinstance(value, dict):
                for key in ("fileUrl", "url", "downloadUrl", "sourceUrl", "ossUrl", "location"):
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                        return candidate
                for nested_key in ("data", "result", "response", "file"):
                    nested = value.get(nested_key)
                    candidate = _pull_url(nested)
                    if candidate:
                        return candidate
            if isinstance(value, list):
                for item in value:
                    candidate = _pull_url(item)
                    if candidate:
                        return candidate
            return ""

        return _pull_url(payload)

    def _prepare_image_inputs(self, image_inputs: list[str]) -> list[str]:
        prepared_inputs = []
        normalized_inputs = self._normalise_image_inputs(image_inputs)

        for index, item in enumerate(normalized_inputs, start=1):
            if item.startswith("data:image/"):
                uploaded_url = self._upload_data_url(item, file_name=f"input-image-{index}.png")
                prepared_inputs.append(uploaded_url)
                continue
            prepared_inputs.append(item)
        return prepared_inputs

    @retry_on_network()
    def _create_task(self, model: str, payload: dict) -> str:
        response = _requests.post(
            f"{self.base_url}/jobs/createTask",
            json={"model": model, "input": payload},
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        task_id = ((response.json().get("data") or {}).get("task_id"))
        if not task_id:
            raise ValueError("KIE task creation failed.")
        return task_id

    @retry_on_network()
    def _create_gpt_image(self, prompt: str) -> list[str]:
        response = _requests.post(
            f"{self.base_url}/gpt/image",
            json={"model": self.text_model, "prompt": prompt},
            headers=self._headers(),
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        urls = self._extract_urls(payload)
        if urls:
            return urls
        data = payload.get("data") or {}
        image_base64 = data.get("b64_json") or data.get("base64")
        if image_base64:
            return [f"data:image/png;base64,{image_base64}"]
        raise ValueError("KIE GPT image request returned no images.")

    @retry_on_network()
    def _create_4o_image_task(self, prompt: str, image_inputs: list[str] | None = None) -> str:
        payload = {
            "prompt": prompt,
            "size": "1:1",
            "isEnhance": False,
            "uploadCn": False,
            "enableFallback": False,
        }
        normalized_inputs = self._prepare_image_inputs(image_inputs or [])
        if normalized_inputs:
            payload["filesUrl"] = normalized_inputs

        response = _requests.post(
            f"{self.base_url}/gpt4o-image/generate",
            json=payload,
            headers=self._headers(),
            timeout=60,
        )
        response.raise_for_status()
        task_id = ((response.json().get("data") or {}).get("taskId"))
        if not task_id:
            raise ValueError("KIE 4o image task creation failed.")
        return task_id

    @retry_on_network()
    def _fetch_task(self, task_id: str) -> dict:
        response = _requests.get(
            f"{self.base_url}/jobs/recordInfo",
            params={"taskId": task_id},
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    @retry_on_network()
    def _fetch_4o_task(self, task_id: str) -> dict:
        response = _requests.get(
            f"{self.base_url}/gpt4o-image/record-info",
            params={"taskId": task_id},
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _extract_urls(self, payload: dict) -> list[str]:
        data = payload.get("data") or {}
        response = data.get("response") or {}
        output = data.get("output") or {}
        urls = []
        for container in (payload, data, response, output):
            if isinstance(container, dict):
                for key in ("resultUrl", "image_url", "imageUrl", "url"):
                    value = container.get(key)
                    if isinstance(value, str):
                        urls.append(value)
        for key in ("resultUrls", "result_urls"):
            value = response.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, str):
                    urls.append(item)
        for key in ("image_urls", "images", "result_urls", "output_urls"):
            value = output.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict):
                    url = item.get("url") or item.get("image_url")
                    if url:
                        urls.append(url)
        return list(dict.fromkeys(urls))

    def _wait_for_output(self, task_id: str) -> list[str]:
        for _ in range(20):
            payload = self._fetch_task(task_id)
            status = str((payload.get("data") or {}).get("status", "")).upper()
            urls = self._extract_urls(payload)
            if urls:
                return urls
            if status in {"FAILED", "ERROR"}:
                raise ValueError("KIE image task failed.")
            time.sleep(2)
        raise TimeoutError("KIE image task timed out.")

    def _wait_for_4o_output(self, task_id: str) -> list[str]:
        for _ in range(45):
            payload = self._fetch_4o_task(task_id)
            status = str((payload.get("data") or {}).get("status", "")).upper()
            urls = self._extract_urls(payload)
            if urls:
                return urls
            if status in {"CREATE_TASK_FAILED", "GENERATE_FAILED", "FAILED", "ERROR"}:
                raise ValueError("KIE 4o image task failed.")
            time.sleep(2)
        raise TimeoutError("KIE 4o image task timed out.")

    def text_to_image(self, prompt: str) -> list[str]:
        if self._uses_4o_endpoint(self.text_model):
            task_id = self._create_4o_image_task(prompt)
            return self._wait_for_4o_output(task_id)
        if (self.text_model or "").lower().startswith("gpt"):
            return self._create_gpt_image(prompt)
        task_id = self._create_task(self.text_model, {"prompt": prompt})
        return self._wait_for_output(task_id)

    def image_to_image(self, prompt: str, image_inputs: list[str]) -> list[str]:
        if self._uses_4o_endpoint(self.edit_model):
            task_id = self._create_4o_image_task(prompt, image_inputs)
            return self._wait_for_4o_output(task_id)
        normalized_inputs = self._prepare_image_inputs(image_inputs)
        payload = {"prompt": prompt}
        model_name = (self.edit_model or "").lower()

        if "banana" in model_name:
            payload["image_input"] = normalized_inputs
        else:
            payload["image_urls"] = normalized_inputs
            payload["input_urls"] = normalized_inputs

        task_id = self._create_task(self.edit_model, payload)
        return self._wait_for_output(task_id)
