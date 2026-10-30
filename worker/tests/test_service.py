"""Tests for service.py (the web service the TypeScript API calls). No database, models or network needed."""
import service
from common.settings import Settings
from starlette.testclient import TestClient

SECRET = "s3cret"
HEADERS = {"x-internal-secret": SECRET}
OWNER = "11111111-1111-1111-1111-111111111111"


def client(monkeypatch, tmp_path, secret=SECRET):
    monkeypatch.setattr(service, "load_settings", lambda: Settings(rag_service_secret=secret, upload_dir=tmp_path))
    return TestClient(service.app)


def chunk(id, document_id=1, name="a.md", position=0, text="text", score=0.5):
    return {"id": id, "document_id": document_id, "name": name, "source": "uploads", "position": position, "text": text, "score": score}


# ----- who may call -----


def test_health_needs_no_secret(monkeypatch, tmp_path):
    assert client(monkeypatch, tmp_path).get("/health").json() == {"ok": True}


def test_every_other_route_refuses_when_no_secret_is_configured(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path, secret="")
    assert c.post("/ask", json={}, headers=HEADERS).status_code == 503
    assert c.post("/index", json={}, headers=HEADERS).status_code == 503


def test_wrong_or_missing_secret_is_refused(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    assert c.post("/ask", json={}).status_code == 401
    assert c.post("/ask", json={}, headers={"x-internal-secret": "nope"}).status_code == 401
    assert c.post("/index", json={"document_id": 1}).status_code == 401


# ----- /index -----


def test_index_rejects_a_bad_body(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    assert c.post("/index", content=b"not json", headers=HEADERS).status_code == 400
    assert c.post("/index", json=[1], headers=HEADERS).status_code == 400
    assert c.post("/index", json={"document_id": "7"}, headers=HEADERS).status_code == 400
    assert c.post("/index", json={"document_id": True}, headers=HEADERS).status_code == 400


def test_index_unknown_document_is_404(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    monkeypatch.setattr(service, "fetch_pending_document", lambda document_id: None)
    assert c.post("/index", json={"document_id": 5}, headers=HEADERS).status_code == 404


def test_index_answers_at_once_then_indexes_the_stored_file(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    document = {"id": 5, "name": "a.md", "file_hash": "h", "storage_path": f"{OWNER}/5.md"}
    calls = []
    monkeypatch.setattr(service, "fetch_pending_document", lambda document_id: document)
    monkeypatch.setattr(service, "index_upload", lambda *args: calls.append(args))
    response = c.post("/index", json={"document_id": 5}, headers=HEADERS)
    assert response.status_code == 202 and response.json() == {"status": "processing"}
    assert calls == [(5, (tmp_path / OWNER / "5.md").resolve(), "a.md", "h")]


def test_a_failed_indexing_is_recorded_on_the_document(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    failures = []
    monkeypatch.setattr(service, "fetch_pending_document", lambda i: {"id": 5, "name": "a.md", "file_hash": "h", "storage_path": "x.md"})
    monkeypatch.setattr(service, "index_upload", lambda *args: 1 / 0)
    monkeypatch.setattr(service, "mark_failed", lambda document_id, message: failures.append((document_id, message)))
    assert c.post("/index", json={"document_id": 5}, headers=HEADERS).status_code == 202
    assert failures[0][0] == 5 and "Could not index" in failures[0][1]


def test_a_stored_path_outside_the_upload_folder_is_never_read(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    calls, failures = [], []
    monkeypatch.setattr(service, "fetch_pending_document", lambda i: {"id": 5, "name": "a.md", "file_hash": "h", "storage_path": "../../etc/passwd"})
    monkeypatch.setattr(service, "index_upload", lambda *args: calls.append(args))
    monkeypatch.setattr(service, "mark_failed", lambda document_id, message: failures.append(document_id))
    c.post("/index", json={"document_id": 5}, headers=HEADERS)
    assert calls == [] and failures == [5]


# ----- /ask -----


def ask(c, **body):
    payload = {"question": "What is it?", "owner_id": OWNER, "document_ids": [1, 2]}
    payload.update(body)
    return c.post("/ask", json=payload, headers=HEADERS)


def test_ask_validates_its_input(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    assert ask(c, question="   ").status_code == 400
    assert ask(c, question="x" * 2001).status_code == 400
    assert ask(c, owner_id="not-a-uuid").status_code == 400
    assert ask(c, owner_id=None).status_code == 400
    assert ask(c, document_ids="1,2").status_code == 400
    assert ask(c, document_ids=[1, "2"]).status_code == 400
    assert ask(c, document_ids=list(range(5001))).status_code == 400


def test_ask_searches_only_the_given_user_and_documents(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    seen = {}
    monkeypatch.setattr(service, "retrieve", lambda question, scope=None: seen.update(question=question, scope=scope) or [])
    ask(c, question="  What is it?  ")
    assert seen == {"question": "What is it?", "scope": {"owner_id": OWNER, "document_ids": [1, 2]}}


def test_nothing_found_means_no_model_call(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    monkeypatch.setattr(service, "retrieve", lambda question, scope=None: [])
    monkeypatch.setattr(service, "answer_from_chunks", lambda q, chunks: 1 / 0)  # must not be reached
    body = ask(c).json()
    assert body == {"answer": "Not found in the documents.", "found": False, "passages": []}


def test_answer_comes_with_numbered_passages_and_the_cited_ones_marked(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    chunks = [chunk(10, 1, "a.md", 0, "alpha", 0.91234567), chunk(11, 2, "b.md", 3, "beta", 0.8)]
    monkeypatch.setattr(service, "retrieve", lambda question, scope=None: chunks)
    monkeypatch.setattr(service, "answer_from_chunks", lambda q, c: {"text": "It is beta [2].", "found": True, "citations": [chunks[1]]})
    body = ask(c).json()
    assert body["answer"] == "It is beta [2]." and body["found"] is True
    assert body["passages"] == [
        {"number": 1, "document_id": 1, "name": "a.md", "part": 1, "text": "alpha", "score": 0.9123, "cited": False},
        {"number": 2, "document_id": 2, "name": "b.md", "part": 4, "text": "beta", "score": 0.8, "cited": True},
    ]


def test_a_failure_while_answering_is_a_502_not_a_crash(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    monkeypatch.setattr(service, "retrieve", lambda question, scope=None: 1 / 0)
    response = ask(c)
    assert response.status_code == 502 and "could not be answered" in response.json()["error"]
