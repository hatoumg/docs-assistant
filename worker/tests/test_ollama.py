import io
import urllib.error
import urllib.request

import pytest

from common.models import build_embedder
from common.ollama import OllamaEmbedder, OllamaError, _http_post
from common.settings import Settings, load_settings


def make(model="nomic-embed-text", dimensions=3, batch_size=32):
    """An embedder whose web calls are recorded instead of sent."""
    calls = []

    def post(url, payload, timeout):
        calls.append((url, payload))
        return {"embeddings": [[0.1] * dimensions for _ in payload["input"]]}

    return OllamaEmbedder("http://localhost:11434/", model, dimensions, batch_size, post=post), calls


def test_request_goes_to_the_embed_address_with_the_model_name():
    embedder, calls = make()
    assert embedder.embed_query("hello") == [0.1, 0.1, 0.1]
    url, payload = calls[0]
    assert url == "http://localhost:11434/api/embed"
    assert payload["model"] == "nomic-embed-text"


def test_nomic_gets_its_document_and_query_labels():
    embedder, calls = make()
    embedder.embed_documents(["alpha"])
    embedder.embed_query("beta")
    assert calls[0][1]["input"] == ["search_document: alpha"]
    assert calls[1][1]["input"] == ["search_query: beta"]


def test_other_models_get_the_text_unchanged():
    embedder, calls = make(model="mxbai-embed-large")
    embedder.embed_documents(["alpha"])
    assert calls[0][1]["input"] == ["alpha"]


def test_a_model_tag_is_ignored_when_choosing_labels():
    embedder, calls = make(model="nomic-embed-text:latest")
    embedder.embed_query("beta")
    assert calls[0][1]["input"] == ["search_query: beta"]


def test_documents_are_sent_in_batches_and_keep_their_order():
    embedder, calls = make(batch_size=4)
    vectors = embedder.embed_documents([f"t{i}" for i in range(10)])
    assert [len(c[1]["input"]) for c in calls] == [4, 4, 2]
    assert len(vectors) == 10


def test_no_texts_means_no_calls():
    embedder, calls = make()
    assert embedder.embed_documents([]) == []
    assert calls == []


def test_wrong_vector_size_is_explained():
    embedder = OllamaEmbedder("http://x", "m", 768, post=lambda url, payload, timeout: {"embeddings": [[0.0] * 384]})
    with pytest.raises(OllamaError) as error:
        embedder.embed_query("q")
    assert "384" in str(error.value) and "768" in str(error.value)


def test_a_reply_with_the_wrong_number_of_vectors_is_rejected():
    embedder = OllamaEmbedder("http://x", "m", 3, post=lambda url, payload, timeout: {"embeddings": [[0.0] * 3]})
    with pytest.raises(OllamaError):
        embedder.embed_documents(["a", "b"])


def test_ollama_not_running_gives_setup_instructions(monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(OllamaError) as error:
        _http_post("http://localhost:11434/api/embed", {"model": "nomic-embed-text", "input": ["x"]}, 5)
    assert "ollama pull nomic-embed-text" in str(error.value)
    assert "ollama.com" in str(error.value)


def test_missing_model_tells_you_to_pull_it(monkeypatch):
    def missing(request, timeout):
        raise urllib.error.HTTPError("http://x", 404, "Not Found", {}, io.BytesIO(b'{"error":"model not found"}'))

    monkeypatch.setattr(urllib.request, "urlopen", missing)
    with pytest.raises(OllamaError) as error:
        _http_post("http://localhost:11434/api/embed", {"model": "nomic-embed-text", "input": ["x"]}, 5)
    assert "ollama pull nomic-embed-text" in str(error.value)


def test_settings_read_the_ollama_address_and_model():
    settings = load_settings({"OLLAMA_URL": "http://box:1234", "EMBED_MODEL": "mxbai-embed-large"})
    assert settings.ollama_url == "http://box:1234"
    assert settings.embed_model == "mxbai-embed-large"
    default = load_settings({})
    assert (default.ollama_url, default.embed_model, default.embed_dim) == ("http://localhost:11434", "nomic-embed-text", 768)


def test_the_default_embedder_is_the_local_one():
    assert isinstance(build_embedder(Settings()), OllamaEmbedder)
