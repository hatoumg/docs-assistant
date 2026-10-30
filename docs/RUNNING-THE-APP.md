# Running the app (website + API + RAG service)

Four things run at once. Open one terminal for each (all commands start in the project folder).

```
Browser ─▶ web (Next.js, :3000) ─▶ api (TypeScript, :4000) ─▶ worker service (Python, :8000) ─▶ Ollama + Postgres
```

## One-time setup

1. **Secrets.** Copy `.env.example` to `.env` (if you have not) and fill in the new block. Make four different random values:
   ```
   node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
   ```
   Use them for `API_JWT_SECRET`, `INTERNAL_SECRET`, `RAG_SERVICE_SECRET` and `AUTH_SECRET`.
2. **Python packages and database.**
   ```
   cd worker
   pip install -r requirements.txt
   docker compose up -d        # from the project folder: starts Postgres with pgvector
   python migrate.py           # applies 003_app.sql (users, folders, owned files)
   ```
3. **Ollama** must be running with the embedding model: `ollama pull nomic-embed-text`.
4. **Node packages.**
   ```
   cd api && npm install
   cd ../web && npm install
   ```

## Every time

| Terminal | Folder | Command |
|---|---|---|
| 1 | `worker` | `uvicorn service:app --port 8000` |
| 2 | `api` | `npm run dev` |
| 3 | `web` | `npm run dev` |

Then open http://localhost:3000, create an account, make a folder, upload `.md`, `.txt` or `.pdf` files into it (PDFs need selectable text; scanned images are not read yet) and ask a question.
A file shows "Reading…" until it has been split and embedded, then "Ready".

## What the chat searches

The chat searches the folder you are in **and every folder inside it, at any depth**. At the top level ("All folders") it searches all of your files. Other people's files are never searched.

## Seeing where an answer came from

Click a citation number in an answer, then **Show in document**. The file opens with the passage highlighted: on the real page for a PDF, in the text for `.md` / `.txt`. If the passage cannot be located exactly, the file still opens and says so.

## Sign in with Google (optional)

The button appears only when both values are set.

1. Go to https://console.cloud.google.com/apis/credentials, create an **OAuth client ID** of type *Web application*.
2. Add the redirect URI `http://localhost:3000/api/auth/callback/google`.
3. Put the client id in `AUTH_GOOGLE_ID` and the secret in `AUTH_GOOGLE_SECRET`, then restart the website.

If someone already registered with a password using the same email, Google sign-in is refused for that email (so nobody can take over an account by registering first).

## Tests

```
cd worker && python -m pytest        # Python (the database tests need Postgres running)
cd api && npm test                   # API (creates and deletes its own temporary databases)
cd web && npm test                   # website helpers and the token check against the API
```

## Troubleshooting

- **"The API is not running"** in the browser: start terminal 2.
- **A file stays "Failed"**: read the red message under it. Usually Ollama is not running or the model is not pulled.
- **Question fails with a 502**: the Python service or the answer model (Groq/Gemini key) is not reachable; look at terminal 1.
- **Login says "Configuration"**: `AUTH_SECRET` is missing in `.env`.
