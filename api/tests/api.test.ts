import assert from "node:assert/strict";
import { access, readdir } from "node:fs/promises";
import path from "node:path";
import { after, before, describe, test } from "node:test";

import { signToken } from "../src/auth/jwt.js";
import { HttpError } from "../src/errors.js";
import { startApp, type TestApp } from "./helpers/harness.js";

let app: TestApp;
before(async () => { app = await startApp(); });
after(async () => { await app.stop(); });

const exists = (p: string) => access(p).then(() => true, () => false);

describe("who may call", () => {
  test("health is open", async () => {
    assert.equal((await app.call("GET", "/health")).status, 200);
  });

  test("unknown pages are 404 and wrong methods are 405", async () => {
    assert.equal((await app.call("GET", "/nope")).status, 404);
    assert.equal((await app.call("PUT", "/api/folders")).status, 405);
  });

  test("/api needs a valid token; the website-only routes need the internal secret", async () => {
    assert.equal((await app.call("GET", "/api/folders")).status, 401);
    assert.equal((await app.call("GET", "/api/folders", { token: "junk" })).status, 401);
    assert.equal((await app.call("GET", "/api/folders", { headers: { authorization: "Basic abc" } })).status, 401);
    assert.equal((await app.call("POST", "/internal/login", { body: { email: "a@b.co", password: "x" } })).status, 401);
    assert.equal((await app.call("POST", "/internal/login", { headers: { "x-internal-secret": "wrong" }, body: {} })).status, 401);
  });

  test("a user token does not open the internal routes, and the internal secret does not open /api", async () => {
    const { token } = await app.register("tokens@example.com");
    assert.equal((await app.call("POST", "/internal/login", { token, body: { email: "tokens@example.com", password: "x" } })).status, 401);
    assert.equal((await app.call("GET", "/api/folders", { headers: { "x-internal-secret": app.config.internalSecret } })).status, 401);
  });

  test("a valid token for a user who no longer exists is refused", async () => {
    const ghost = signToken("99999999-9999-9999-9999-999999999999", app.config.apiJwtSecret, 60, () => app.clock.now);
    assert.equal((await app.call("GET", "/api/me", { token: ghost })).status, 401);
  });

  test("an expired token is refused", async () => {
    const { id } = await app.register("expired@example.com");
    const old = signToken(id, app.config.apiJwtSecret, 60, () => app.clock.now - 3_600_000);
    assert.equal((await app.call("GET", "/api/me", { token: old })).status, 401);
  });

  test("/api/me returns the signed-in user and never the password hash", async () => {
    const { token } = await app.register("me@example.com");
    const me = await app.call("GET", "/api/me", { token });
    assert.equal(me.json.user.email, "me@example.com");
    assert.equal("password_hash" in me.json.user, false);
  });
});

describe("accounts", () => {
  test("register, then login with the same password", async () => {
    const created = await app.call("POST", "/internal/register", { internal: true, body: { email: "New.User@Example.com", password: "a long password", name: "New" } });
    assert.equal(created.status, 201);
    assert.deepEqual(Object.keys(created.json).sort(), ["email", "id", "name"]);
    assert.equal(created.json.email, "new.user@example.com");
    const login = await app.call("POST", "/internal/login", { internal: true, body: { email: "NEW.user@example.com", password: "a long password" } });
    assert.equal(login.status, 200);
    assert.equal(login.json.id, created.json.id);
  });

  test("the same email cannot register twice, in any capitalisation", async () => {
    await app.register("dup@example.com");
    const again = await app.call("POST", "/internal/register", { internal: true, body: { email: "DUP@example.com", password: "another password" } });
    assert.equal(again.status, 409);
  });

  test("bad registration input is rejected", async () => {
    for (const body of [{}, { email: "nope", password: "long enough pw" }, { email: "a@b.co", password: "short" }, { email: "a@b.co", password: "x".repeat(129) }, { email: 5, password: "long enough pw" }]) {
      assert.equal((await app.call("POST", "/internal/register", { internal: true, body })).status, 400);
    }
  });

  test("the password is stored hashed, never as typed", async () => {
    await app.register("hashed@example.com", "plain text secret");
    const row = await app.db.query<{ password_hash: string }>("SELECT password_hash FROM users WHERE email = 'hashed@example.com'");
    assert.match(row.rows[0]!.password_hash, /^scrypt\$/);
    assert.equal(row.rows[0]!.password_hash.includes("plain text secret"), false);
  });

  test("wrong password and unknown email give the same answer", async () => {
    await app.register("known@example.com");
    const wrong = await app.call("POST", "/internal/login", { internal: true, body: { email: "known@example.com", password: "not the password" } });
    const unknown = await app.call("POST", "/internal/login", { internal: true, body: { email: "nobody@example.com", password: "not the password" } });
    assert.equal(wrong.status, 401);
    assert.equal(unknown.status, 401);
    assert.deepEqual(wrong.json, unknown.json);
  });

  test("five wrong passwords lock that email for a while, then it recovers", async () => {
    await app.register("locked@example.com", "the right password");
    const attempt = (password: string) => app.call("POST", "/internal/login", { internal: true, body: { email: "locked@example.com", password } });
    for (let i = 0; i < 5; i++) assert.equal((await attempt("wrong password")).status, 401);
    assert.equal((await attempt("the right password")).status, 429);
    app.clock.now += 16 * 60_000;
    assert.equal((await attempt("the right password")).status, 200);
  });

  test("Google sign-in creates an account, then finds it again", async () => {
    const body = { provider: "google", providerAccountId: "g-1", email: "g@example.com", emailVerified: true, name: "G" };
    const first = await app.call("POST", "/internal/oauth", { internal: true, body });
    const second = await app.call("POST", "/internal/oauth", { internal: true, body });
    assert.equal(first.status, 200);
    assert.equal(first.json.id, second.json.id);
  });

  test("Google sign-in never takes over an existing password account, and needs a verified email", async () => {
    const owner = await app.register("taken@example.com");
    const attempt = await app.call("POST", "/internal/oauth", { internal: true, body: { provider: "google", providerAccountId: "g-2", email: "taken@example.com", emailVerified: true } });
    assert.equal(attempt.status, 409);
    const me = await app.call("GET", "/api/me", { token: owner.token });
    assert.equal(me.json.user.email, "taken@example.com");
    const unverified = await app.call("POST", "/internal/oauth", { internal: true, body: { provider: "google", providerAccountId: "g-3", email: "new2@example.com", emailVerified: false } });
    assert.equal(unverified.status, 403);
    const badProvider = await app.call("POST", "/internal/oauth", { internal: true, body: { provider: "github", providerAccountId: "x", email: "x@example.com", emailVerified: true } });
    assert.equal(badProvider.status, 400);
  });

  test("a Google-only account cannot log in with a password", async () => {
    await app.call("POST", "/internal/oauth", { internal: true, body: { provider: "google", providerAccountId: "g-4", email: "gonly@example.com", emailVerified: true } });
    const login = await app.call("POST", "/internal/login", { internal: true, body: { email: "gonly@example.com", password: "anything at all" } });
    assert.equal(login.status, 401);
  });
});

describe("folders", () => {
  test("top level starts empty; create, nest, and list contents with breadcrumbs", async () => {
    const { token } = await app.register("folders1@example.com");
    assert.deepEqual((await app.call("GET", "/api/folders", { token })).json, { folder: null, breadcrumbs: [], folders: [], files: [] });
    const contracts = await app.folder(token, "Contracts");
    const y2024 = await app.folder(token, "2024", contracts);
    const q1 = await app.folder(token, "Q1", y2024);
    const top = await app.call("GET", "/api/folders", { token });
    assert.deepEqual(top.json.folders.map((f: any) => f.name), ["Contracts"]);
    const inside = await app.call("GET", `/api/folders?parent=${q1}`, { token });
    assert.deepEqual(inside.json.breadcrumbs.map((b: any) => b.name), ["Contracts", "2024", "Q1"]);
    assert.equal(inside.json.folder.parentId, y2024);
    const mid = await app.call("GET", `/api/folders?parent=${y2024}`, { token });
    assert.deepEqual(mid.json.folders.map((f: any) => f.name), ["Q1"]);
  });

  test("folders are listed A to Z ignoring capitals", async () => {
    const { token } = await app.register("folders2@example.com");
    for (const name of ["banana", "Cherry", "apple"]) await app.folder(token, name);
    assert.deepEqual((await app.call("GET", "/api/folders", { token })).json.folders.map((f: any) => f.name), ["apple", "banana", "Cherry"]);
  });

  test("the same name twice in one place is refused; elsewhere it is fine", async () => {
    const { token } = await app.register("folders3@example.com");
    const a = await app.folder(token, "Notes");
    const dup = await app.call("POST", "/api/folders", { token, body: { name: " notes " } });
    assert.equal(dup.status, 409);
    assert.equal((await app.call("POST", "/api/folders", { token, body: { name: "Notes", parentId: a } })).status, 201);
  });

  test("bad names and bad parents are rejected", async () => {
    const { token } = await app.register("folders4@example.com");
    for (const name of ["", "   ", "a/b", "x".repeat(121), 5]) assert.equal((await app.call("POST", "/api/folders", { token, body: { name } })).status, 400);
    assert.equal((await app.call("POST", "/api/folders", { token, body: { name: "X", parentId: "not-an-id" } })).status, 404);
    assert.equal((await app.call("POST", "/api/folders", { token, body: { name: "X", parentId: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" } })).status, 404);
    assert.equal((await app.call("POST", "/api/folders", { token, raw: "not json" })).status, 400);
  });

  test("deleting a folder removes everything below it, including files on disk and their chunks", async () => {
    const { token } = await app.register("folders5@example.com");
    const top = await app.folder(token, "Top");
    const sub = await app.folder(token, "Sub", top);
    const keep = await app.folder(token, "Keep");
    const deep = await app.upload(token, sub, "deep.md");
    const kept = await app.upload(token, keep, "kept.md");
    const deepPath = (await app.db.query<{ storage_path: string }>("SELECT storage_path FROM documents WHERE id = $1", [deep.json.file.id])).rows[0]!.storage_path;
    await app.db.query("INSERT INTO chunks (document_id, position, text, embedding) VALUES ($1, 0, 't', array_fill(0.1::real, ARRAY[768])::vector)", [deep.json.file.id]);
    assert.equal(await exists(path.join(app.config.uploadDir, deepPath)), true);

    assert.equal((await app.call("DELETE", `/api/folders/${top}`, { token })).status, 204);
    assert.equal((await app.call("GET", `/api/folders?parent=${sub}`, { token })).status, 404);
    assert.equal(await exists(path.join(app.config.uploadDir, deepPath)), false);
    assert.equal((await app.db.query("SELECT 1 FROM chunks WHERE document_id = $1", [deep.json.file.id])).rowCount, 0);
    assert.equal((await app.call("GET", `/api/files/${kept.json.file.id}`, { token })).status, 200);
    assert.equal((await app.call("DELETE", `/api/folders/${top}`, { token })).status, 404);
  });
});

describe("files", () => {
  test("upload stores the file, indexes it, and it shows in the folder", async () => {
    const { token } = await app.register("files1@example.com");
    const folder = await app.folder(token, "Docs");
    const uploaded = await app.upload(token, folder, "Guide.md", "# Guide\nHello there.");
    assert.equal(uploaded.status, 202);
    assert.equal(uploaded.json.file.name, "Guide.md");
    assert.equal(uploaded.json.file.status, "processing");
    assert.equal(app.rag.indexed.at(-1), uploaded.json.file.id);
    const listing = await app.call("GET", `/api/folders?parent=${folder}`, { token });
    assert.equal(listing.json.files[0].name, "Guide.md");
    assert.equal(listing.json.files[0].status, "ready");
    assert.equal(listing.json.files[0].sizeBytes, 20);
    assert.equal("storage_path" in listing.json.files[0], false);
    const content = await app.call("GET", `/api/files/${uploaded.json.file.id}/content`, { token });
    assert.equal(content.text, "# Guide\nHello there.");
    assert.match(content.headers.get("content-type") ?? "", /^text\/plain/);
  });

  test("a failed handover to the indexing service is shown on the file", async () => {
    const { token } = await app.register("files2@example.com");
    const folder = await app.folder(token, "Docs");
    app.rag.indexError = new HttpError(502, "rag_unavailable", "The answering service is not reachable. Is it running?");
    const uploaded = await app.upload(token, folder, "a.md");
    app.rag.indexError = null;
    assert.equal(uploaded.status, 202);
    assert.equal(uploaded.json.file.status, "failed");
    assert.match(uploaded.json.file.error, /not reachable/);
    const stored = await app.db.query<{ status: string }>("SELECT status FROM documents WHERE id = $1", [uploaded.json.file.id]);
    assert.equal(stored.rows[0]!.status, "failed");
  });

  test("only .md and .txt, text only, not empty, not too big", async () => {
    const { token } = await app.register("files3@example.com");
    const folder = await app.folder(token, "Docs");
    assert.equal((await app.upload(token, folder, "a.docx")).status, 415);
    assert.equal((await app.upload(token, folder, "fake.pdf", "just text, not a pdf")).status, 415);
    assert.equal((await app.upload(token, folder, "noextension")).status, 415);
    assert.equal((await app.upload(token, folder, "../evil.md")).status, 400);
    assert.equal((await app.upload(token, folder, "a.md", "")).status, 400);
    assert.equal((await app.upload(token, folder, "b.md", "   \n  ")).status, 400);
    assert.equal((await app.upload(token, folder, "c.txt", "bin\u0000ary")).status, 415);
    // The server answers 413 and hangs up while the client is still sending, so on some systems (Windows)
    // the client sees a reset connection instead of the 413. Either way the file must be refused and not kept.
    const tooBig = await app.upload(token, folder, "big.md", "x".repeat(app.config.maxUploadBytes + 1)).catch(() => ({ status: 413 }));
    assert.equal(tooBig.status, 413);
    assert.equal((await app.call("GET", `/api/folders?parent=${folder}`, { token })).json.files.length, 0);
  });

  test("a PDF is stored as it is, indexed, and can be downloaded again", async () => {
    const { token } = await app.register("pdf1@example.com");
    const folder = await app.folder(token, "Docs");
    const bytes = Buffer.concat([Buffer.from("%PDF-1.4\n"), Buffer.from([0, 1, 2, 255, 254]), Buffer.from("\n%%EOF\n")]);
    const uploaded = await app.upload(token, folder, "terms.pdf", bytes);
    assert.equal(uploaded.status, 202);
    assert.ok(app.rag.indexed.includes(uploaded.json.file.id));
    const content = await app.call("GET", `/api/files/${uploaded.json.file.id}/content`, { token });
    assert.equal(content.status, 200);
    assert.equal(content.headers.get("content-type"), "application/pdf");
  });

  test("the same name in a folder is refused, and the refused file is not left on disk", async () => {
    const { id, token } = await app.register("files4@example.com");
    const folder = await app.folder(token, "Docs");
    assert.equal((await app.upload(token, folder, "same.md", "one")).status, 202);
    assert.equal((await app.upload(token, folder, "SAME.md", "two")).status, 409);
    assert.equal((await readdir(path.join(app.config.uploadDir, id))).length, 1);
  });

  test("the per-user file limit is enforced", async () => {
    const limited = await startApp({ maxFilesPerUser: 2 });
    try {
      const { token } = await limited.register("limit@example.com");
      const folder = await limited.folder(token, "Docs");
      assert.equal((await limited.upload(token, folder, "a.md")).status, 202);
      assert.equal((await limited.upload(token, folder, "b.md")).status, 202);
      assert.equal((await limited.upload(token, folder, "c.md")).status, 409);
    } finally {
      await limited.stop();
    }
  });

  test("deleting a file removes the row, its chunks and the stored copy", async () => {
    const { token } = await app.register("files5@example.com");
    const folder = await app.folder(token, "Docs");
    const uploaded = await app.upload(token, folder, "gone.md");
    const id = uploaded.json.file.id;
    const stored = (await app.db.query<{ storage_path: string }>("SELECT storage_path FROM documents WHERE id = $1", [id])).rows[0]!.storage_path;
    await app.db.query("INSERT INTO chunks (document_id, position, text, embedding) VALUES ($1, 0, 't', array_fill(0.1::real, ARRAY[768])::vector)", [id]);
    assert.equal((await app.call("DELETE", `/api/files/${id}`, { token })).status, 204);
    assert.equal((await app.db.query("SELECT 1 FROM chunks WHERE document_id = $1", [id])).rowCount, 0);
    assert.equal(await exists(path.join(app.config.uploadDir, stored)), false);
    assert.equal((await app.call("GET", `/api/files/${id}`, { token })).status, 404);
    assert.equal((await app.call("DELETE", `/api/files/${id}`, { token })).status, 404);
  });

  test("odd file ids are 'not found'", async () => {
    const { token } = await app.register("files6@example.com");
    for (const bad of ["abc", "0", "-5", "1e3", "99999999999999", "%E0%A4%A"]) assert.equal((await app.call("GET", `/api/files/${bad}`, { token })).status, 404);
  });
});

describe("one user can never reach another user's data", () => {
  let alice: { id: string; token: string };
  let bob: { id: string; token: string };
  let aliceFolder: string;
  let aliceFile: number;
  before(async () => {
    alice = await app.register("alice-iso@example.com");
    bob = await app.register("bob-iso@example.com");
    aliceFolder = await app.folder(alice.token, "Private");
    aliceFile = (await app.upload(alice.token, aliceFolder, "secret.md", "alice's secret")).json.file.id;
  });

  test("Bob cannot list, read, upload into, create inside or delete Alice's things", async () => {
    assert.equal((await app.call("GET", `/api/folders?parent=${aliceFolder}`, { token: bob.token })).status, 404);
    assert.equal((await app.call("POST", "/api/folders", { token: bob.token, body: { name: "x", parentId: aliceFolder } })).status, 404);
    assert.equal((await app.upload(bob.token, aliceFolder, "sneak.md")).status, 404);
    assert.equal((await app.call("GET", `/api/files/${aliceFile}`, { token: bob.token })).status, 404);
    assert.equal((await app.call("GET", `/api/files/${aliceFile}/content`, { token: bob.token })).status, 404);
    assert.equal((await app.call("DELETE", `/api/files/${aliceFile}`, { token: bob.token })).status, 404);
    assert.equal((await app.call("DELETE", `/api/folders/${aliceFolder}`, { token: bob.token })).status, 404);
    assert.equal((await app.call("POST", "/api/chat", { token: bob.token, body: { question: "secret?", folderId: aliceFolder } })).status, 404);
    // ...and everything is still there for Alice
    assert.equal((await app.call("GET", `/api/files/${aliceFile}/content`, { token: alice.token })).text, "alice's secret");
  });

  test("Bob's chat never includes Alice's files, even at the top level", async () => {
    app.rag.asked = [];
    const bobFolder = await app.folder(bob.token, "Mine");
    const bobFile = (await app.upload(bob.token, bobFolder, "bob.md")).json.file.id;
    const reply = await app.call("POST", "/api/chat", { token: bob.token, body: { question: "What is in here?" } });
    assert.equal(reply.status, 200);
    assert.deepEqual(app.rag.asked.at(-1)!.documentIds, [bobFile]);
    assert.equal(app.rag.asked.at(-1)!.ownerId, bob.id);
  });

  test("the same file name and contents in two accounts is fine", async () => {
    const carol = await app.register("carol-iso@example.com");
    const folder = await app.folder(carol.token, "Private");
    assert.equal((await app.upload(carol.token, folder, "secret.md", "alice's secret")).status, 202);
  });
});

describe("chat searches the folder you are in and everything inside it", () => {
  test("a folder's question covers that folder and all subfolders, and nothing else", async () => {
    const { id, token } = await app.register("chat1@example.com");
    const contracts = await app.folder(token, "Contracts");
    const y2024 = await app.folder(token, "2024", contracts);
    const q1 = await app.folder(token, "Q1", y2024);
    const notes = await app.folder(token, "Notes");
    const idOf = async (folder: string, name: string) => (await app.upload(token, folder, name)).json.file.id as number;
    const a = await idOf(contracts, "a.md");
    const b = await idOf(y2024, "b.md");
    const c = await idOf(q1, "c.md");
    const n = await idOf(notes, "n.md");

    const ask = async (folderId?: string) => {
      const reply = await app.call("POST", "/api/chat", { token, body: { question: "Summarise", folderId } });
      assert.equal(reply.status, 200);
      return [...app.rag.asked.at(-1)!.documentIds].sort((x, y) => x - y);
    };
    const sorted = (...ids: number[]) => ids.sort((x, y) => x - y);
    assert.deepEqual(await ask(contracts), sorted(a, b, c));
    assert.deepEqual(await ask(y2024), sorted(b, c));
    assert.deepEqual(await ask(q1), [c]);
    assert.deepEqual(await ask(notes), [n]);
    assert.deepEqual(await ask(), sorted(a, b, c, n)); // top level = everything of mine
    assert.equal(app.rag.asked.at(-1)!.ownerId, id);
  });

  test("files still processing or failed are not searched, and the reply says so", async () => {
    const { token } = await app.register("chat2@example.com");
    const folder = await app.folder(token, "Docs");
    const ready = (await app.upload(token, folder, "ready.md")).json.file.id;
    app.rag.finishIndexing = false;
    await app.upload(token, folder, "busy.md");
    app.rag.finishIndexing = true;
    app.rag.indexError = new HttpError(502, "rag_unavailable", "down");
    await app.upload(token, folder, "broken.md");
    app.rag.indexError = null;
    const reply = await app.call("POST", "/api/chat", { token, body: { question: "Anything?", folderId: folder } });
    assert.deepEqual(app.rag.asked.at(-1)!.documentIds, [ready]);
    assert.deepEqual(reply.json.searched, { files: 1, processing: 1, failed: 1 });
  });

  test("with nothing searchable the model is not called and the user is told what to do", async () => {
    const { token } = await app.register("chat3@example.com");
    const folder = await app.folder(token, "Empty");
    const before = app.rag.asked.length;
    const reply = await app.call("POST", "/api/chat", { token, body: { question: "Hello?", folderId: folder } });
    assert.equal(reply.status, 200);
    assert.equal(reply.json.found, false);
    assert.match(reply.json.answer, /Upload/);
    assert.equal(app.rag.asked.length, before);
  });

  test("citations carry the file and the folder they came from, so the website can link to them", async () => {
    const { token } = await app.register("chat4@example.com");
    const outer = await app.folder(token, "Outer");
    const inner = await app.folder(token, "Inner", outer);
    const fileId = (await app.upload(token, inner, "deep.md")).json.file.id;
    const reply = await app.call("POST", "/api/chat", { token, body: { question: "Where?", folderId: outer } });
    assert.deepEqual(reply.json.passages[0], { number: 1, fileId, folderId: inner, name: `file${fileId}.md`, part: 1, text: `text ${fileId}`, score: 0.9, cited: true });
    assert.equal(reply.json.answer, "It says so [1].");
  });

  test("bad questions are rejected", async () => {
    const { token } = await app.register("chat5@example.com");
    for (const question of ["", "   ", 5, null, "x".repeat(2001)]) {
      assert.equal((await app.call("POST", "/api/chat", { token, body: { question } })).status, 400);
    }
    assert.equal((await app.call("POST", "/api/chat", { token, body: { question: "Hi", folderId: "nonsense" } })).status, 404);
  });

  test("a failure in the answering service becomes a clear 502", async () => {
    const { token } = await app.register("chat6@example.com");
    const folder = await app.folder(token, "Docs");
    await app.upload(token, folder, "a.md");
    app.rag.askError = new HttpError(502, "rag_failed", "Could not reach Ollama.");
    const reply = await app.call("POST", "/api/chat", { token, body: { question: "Hi?", folderId: folder } });
    app.rag.askError = null;
    assert.equal(reply.status, 502);
    assert.match(reply.json.message, /Ollama/);
  });

  test("a user is limited to 20 questions a minute", async () => {
    const { token } = await app.register("chat7@example.com");
    const folder = await app.folder(token, "Docs");
    await app.upload(token, folder, "a.md");
    const send = () => app.call("POST", "/api/chat", { token, body: { question: "Hi?", folderId: folder } });
    for (let i = 0; i < 20; i++) assert.equal((await send()).status, 200);
    assert.equal((await send()).status, 429);
    app.clock.now += 61_000;
    assert.equal((await send()).status, 200);
  });
});

describe("responses are safe to show", () => {
  test("errors never include internals and every response says nosniff and no-store", async () => {
    const res = await app.call("GET", "/api/folders");
    assert.equal(res.headers.get("x-content-type-options"), "nosniff");
    assert.equal(res.headers.get("cache-control"), "no-store");
    assert.equal(res.text.includes("at "), false);
  });

  test("uploaded text is served as plain text, never as a page", async () => {
    const { token } = await app.register("safe1@example.com");
    const folder = await app.folder(token, "Docs");
    const file = (await app.upload(token, folder, "x.md", "<script>alert(1)</script>")).json.file.id;
    const content = await app.call("GET", `/api/files/${file}/content`, { token });
    assert.match(content.headers.get("content-type") ?? "", /^text\/plain/);
    assert.equal(content.text, "<script>alert(1)</script>");
  });
});
