"""A small web service that lets the TypeScript API use the RAG pipeline.

Run it from the worker folder:

    uvicorn service:app --port 8000

It has two jobs, and only the API is allowed to ask for them (see RAG_SERVICE_SECRET in .env):

    POST /index   index a file the API has already saved             -> starts the work, answers at once
    POST /ask     answer a question from some of one user's files    -> {"answer", "found", "passages"}

The API decides WHICH documents a question may look at (a folder and everything inside it).
The service only searches the ids it is given, and only inside that user's files.
"""
import hmac
import uuid

from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Route

from common.database import connect
from common.loader import load
from common.settings import load_settings

index_upload = load("1_indexing.main", "index_upload")
retrieve = load("2_retrieval.main", "retrieve")
answer_from_chunks = load("3_generation.main", "answer_from_chunks")
mark_failed = load("1_indexing.5_store", "mark_failed")

MAX_QUESTION_CHARS = 2000
MAX_DOCUMENT_IDS = 5000


class BadRequest(Exception):
    pass


# ----- who may call -----


def check_caller(request):
    """Returns an error response if the caller is not the API, otherwise None. Refuses everything if no secret is set."""
    secret = load_settings().rag_service_secret
    if not secret:
        return JSONResponse({"error": "RAG_SERVICE_SECRET is not set, so the service refuses all requests."}, status_code=503)
    sent = request.headers.get("x-internal-secret", "")
    if not hmac.compare_digest(sent.encode(), secret.encode()):
        return JSONResponse({"error": "not allowed"}, status_code=401)
    return None


async def read_json(request):
    try:
        body = await request.json()
    except ValueError:
        raise BadRequest("The body must be JSON.") from None
    if not isinstance(body, dict):
        raise BadRequest("The body must be a JSON object.")
    return body


def whole_number(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadRequest(f"{label} must be a whole number.")
    return value


# ----- indexing -----


def fetch_pending_document(document_id):
    """The row of an uploaded file that is waiting to be indexed, or None."""
    connection = connect()
    row = connection.execute(
        "SELECT id, name, file_hash, storage_path FROM documents WHERE id = %s AND owner_id IS NOT NULL AND status = 'processing'",
        (document_id,),
    ).fetchone()
    connection.close()
    return None if row is None else {"id": row[0], "name": row[1], "file_hash": row[2], "storage_path": row[3]}


def path_inside_uploads(storage_path):
    """The real path of a stored file, refusing anything that points outside the upload folder."""
    root = load_settings().upload_dir.resolve()
    path = (root / storage_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("The stored path is outside the upload folder.")
    return path


def run_indexing(document):
    """Runs after the response has been sent. Any failure is saved on the document so the user can see it."""
    try:
        index_upload(document["id"], path_inside_uploads(document["storage_path"]), document["name"], document["file_hash"])
    except Exception as error:
        print(f"Indexing document {document['id']} failed: {error!r}")
        mark_failed(document["id"], f"Could not index this file: {error}")


async def index_endpoint(request):
    denied = check_caller(request)
    if denied:
        return denied
    try:
        body = await read_json(request)
        document_id = whole_number(body.get("document_id"), "document_id")
    except BadRequest as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    document = await run_in_threadpool(fetch_pending_document, document_id)
    if document is None:
        return JSONResponse({"error": "No uploaded file with that id is waiting to be indexed."}, status_code=404)
    return JSONResponse({"status": "processing"}, status_code=202, background=BackgroundTask(run_indexing, document))


# ----- asking -----


def parse_ask(body):
    question = body.get("question")
    if not isinstance(question, str) or not question.strip():
        raise BadRequest("question must be some text.")
    if len(question) > MAX_QUESTION_CHARS:
        raise BadRequest(f"question is longer than {MAX_QUESTION_CHARS} characters.")
    try:
        owner_id = str(uuid.UUID(str(body.get("owner_id"))))
    except ValueError:
        raise BadRequest("owner_id must be a user id.") from None
    ids = body.get("document_ids")
    if not isinstance(ids, list) or len(ids) > MAX_DOCUMENT_IDS:
        raise BadRequest(f"document_ids must be a list of at most {MAX_DOCUMENT_IDS} ids.")
    return question.strip(), {"owner_id": owner_id, "document_ids": [whole_number(i, "document_ids") for i in ids]}


def passages_for_display(chunks, cited):
    """The retrieved chunks, numbered the way the model saw them, so [2] in the answer points to passage 2."""
    cited_ids = {chunk["id"] for chunk in cited}
    return [
        {
            "number": number,
            "document_id": chunk["document_id"],
            "name": chunk["name"],
            "part": chunk["position"] + 1,
            "text": chunk["text"],
            "score": round(chunk["score"], 4),
            "cited": chunk["id"] in cited_ids,
        }
        for number, chunk in enumerate(chunks, start=1)
    ]


def answer(question, scope):
    chunks = retrieve(question, scope=scope)
    if not chunks:  # nothing to read, so do not spend a model call
        return {"answer": "Not found in the documents.", "found": False, "passages": []}
    result = answer_from_chunks(question, chunks)
    return {"answer": result["text"], "found": result["found"], "passages": passages_for_display(chunks, result["citations"])}


async def ask_endpoint(request):
    denied = check_caller(request)
    if denied:
        return denied
    try:
        question, scope = parse_ask(await read_json(request))
    except BadRequest as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    try:
        return JSONResponse(await run_in_threadpool(answer, question, scope))
    except Exception as error:  # Ollama stopped, the model refused, the database is down...
        print(f"Question failed: {error!r}")
        return JSONResponse({"error": f"The question could not be answered: {error}"}, status_code=502)


async def health_endpoint(request):
    return JSONResponse({"ok": True})


app = Starlette(
    routes=[
        Route("/health", health_endpoint, methods=["GET"]),
        Route("/index", index_endpoint, methods=["POST"]),
        Route("/ask", ask_endpoint, methods=["POST"]),
    ]
)
