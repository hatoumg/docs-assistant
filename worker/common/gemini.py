"""Gemini implementations of the Embedder and LLM ports. The only place that imports google-genai."""
import re
import time

from common.retry import call_with_retries
from common.throttle import TokenWindow
from common.usage import UsageMeter

def is_transient(error) -> bool:
    """Worth retrying: rate limits, server-side errors, or no HTTP code at all (network trouble).

    A 400, 401, 403 or 404 means the request itself is wrong (bad key, unknown model), so waiting cannot fix it.
    """
    code = getattr(error, "code", None)
    return not isinstance(code, int) or code == 429 or code >= 500


def suggested_wait(error):
    """Read "Please retry in 58.5s" (or retryDelay '58s') out of a Google rate-limit error. None if absent."""
    match = re.search(r"retry in\s+([\d.]+)s|retryDelay['\"]?:\s*['\"]([\d.]+)s", str(error))
    if not match:
        return None
    return min(float(match.group(1) or match.group(2)) + 1.0, 90.0)


DOCUMENT_TASK = "RETRIEVAL_DOCUMENT"
QUERY_TASK = "RETRIEVAL_QUERY"


def _client(api_key: str):
    from google import genai

    return genai.Client(api_key=api_key)


class GeminiEmbedder:
    def __init__(self, api_key, model, dimensions, batch_size=50, pause_seconds=1.0, retries=5, usage=None, tokens_per_minute=0, chars_per_token=3.0):
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._pause = pause_seconds
        self._retries = retries
        self._usage = usage or UsageMeter()
        self._client_instance = None
        self._window = TokenWindow(tokens_per_minute) if tokens_per_minute else None
        self._chars_per_token = chars_per_token

    @property
    def model_id(self) -> str:
        return f"{self._model}|{self._dimensions}"

    def _client_(self):
        if self._client_instance is None:
            self._client_instance = _client(self._api_key)
        return self._client_instance

    def _embed(self, texts, task_type):
        from google.genai import types

        def call():
            result = self._client_().models.embed_content(
                model=self._model,
                contents=texts,
                config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self._dimensions),
            )
            return [list(e.values) for e in result.embeddings]

        vectors = call_with_retries(call, tries=self._retries, retryable=is_transient, wait_hint=suggested_wait)
        self._usage.embed_calls += 1
        return vectors

    def _estimate(self, text: str) -> int:
        return int(len(text) / self._chars_per_token) + 1

    def _batches(self, texts):
        """Group texts so each batch has at most batch_size items and fits within the per-minute token limit."""
        budget = int(self._window.limit * 0.9) if self._window else None
        batch, tokens = [], 0
        for text in texts:
            cost = self._estimate(text)
            if batch and (len(batch) >= self._batch_size or (budget and tokens + cost > budget)):
                yield batch, tokens
                batch, tokens = [], 0
            batch.append(text)
            tokens += cost
        if batch:
            yield batch, tokens

    def embed_documents(self, texts: list) -> list:
        vectors = []
        for batch, tokens in self._batches(texts):
            if self._window:
                self._window.wait_for(tokens)
            vectors.extend(self._embed(batch, DOCUMENT_TASK))
            time.sleep(self._pause)
        return vectors

    def embed_query(self, text: str) -> list:
        return self._embed([text], QUERY_TASK)[0]


class GeminiLLM:
    def __init__(self, api_key, model, retries=5, usage=None):
        self._api_key = api_key
        self._model = model
        self._retries = retries
        self._usage = usage or UsageMeter()
        self._client_instance = None

    @property
    def model_id(self) -> str:
        return self._model

    def complete(self, prompt: str) -> str:
        from google.genai import types

        if self._client_instance is None:
            self._client_instance = _client(self._api_key)

        def call():
            response = self._client_instance.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return response.text or ""

        text = call_with_retries(call, tries=self._retries, retryable=is_transient, wait_hint=suggested_wait)
        self._usage.llm_calls += 1
        return text
