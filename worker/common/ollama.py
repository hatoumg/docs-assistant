"""Embeddings from Ollama, a free program that runs AI models on your own computer.

There is no account, key or daily limit. Our code sends text to Ollama's local web address
(http://localhost:11434 by default) and gets back a list of numbers for each text.

One-time setup:  install Ollama from https://ollama.com, then run:  ollama pull nomic-embed-text
Uses only the standard library, so there is nothing extra to pip install.
"""
import json
import urllib.error
import urllib.request

# Some models need a short label in front of the text to tell them what it is for.
# nomic-embed-text was trained that way and finds better matches with the labels.
PREFIXES = {"nomic-embed-text": ("search_document: ", "search_query: ")}


class OllamaError(RuntimeError):
    pass


def _http_post(url, payload, timeout):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:200]
        if error.code == 404:
            raise OllamaError(f"Ollama does not have this model yet ({detail}). Download it with:  ollama pull {payload['model']}") from None
        raise OllamaError(f"Ollama returned HTTP {error.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise OllamaError(
            f"Could not reach Ollama at {url} ({error}). Install it from https://ollama.com, make sure it is running, "
            f"then run:  ollama pull {payload['model']}"
        ) from None


class OllamaEmbedder:
    def __init__(self, base_url, model, dimensions, batch_size=32, post=_http_post, timeout=300):
        self._url = base_url.rstrip("/") + "/api/embed"
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._post = post
        self._timeout = timeout  # generous: the first call has to load the model into memory
        self._document_prefix, self._query_prefix = PREFIXES.get(model.split(":")[0], ("", ""))

    def _embed(self, texts):
        data = self._post(self._url, {"model": self._model, "input": texts}, self._timeout)
        vectors = data.get("embeddings") if isinstance(data, dict) else None
        if not vectors or len(vectors) != len(texts):
            raise OllamaError(f"Unexpected reply from Ollama: {str(data)[:200]}")
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise OllamaError(
                    f"Model '{self._model}' makes vectors of {len(vector)} numbers, but the database expects "
                    f"{self._dimensions}. Pick a {self._dimensions}-number model or change the table size."
                )
        return vectors

    def embed_documents(self, texts: list) -> list:
        vectors = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(self._embed([self._document_prefix + text for text in batch]))
        return vectors

    def embed_query(self, text: str) -> list:
        return self._embed([self._query_prefix + text])[0]
