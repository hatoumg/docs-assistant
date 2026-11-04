import { mkdtemp, rm } from "node:fs/promises";
import http from "node:http";
import type { AddressInfo } from "node:net";
import os from "node:os";
import path from "node:path";

import { createApp } from "../../src/app.js";
import { signToken } from "../../src/auth/jwt.js";
import type { Config } from "../../src/config.js";
import type { Db } from "../../src/db.js";
import { HttpError } from "../../src/errors.js";
import type { Answer, RagClient } from "../../src/ragClient.js";

export const SECRETS = {
  apiJwtSecret: "a".repeat(40),
  internalSecret: "b".repeat(40),
  ragServiceSecret: "c".repeat(40),
};

// Each test file gets its own fresh database. (TEST_DB_MODULE lets a different environment supply its own.)
const { createTestDatabase } = await import(process.env.TEST_DB_MODULE ?? "./testDb.js");

/** Stands in for the Python service. By default "indexing" finishes at once, as the real service would shortly after. */
export class FakeRag implements RagClient {
  indexed: number[] = [];
  asked: { question: string; ownerId: string; documentIds: number[] }[] = [];
  indexError: HttpError | null = null;
  askError: HttpError | null = null;
  finishIndexing = true;
  constructor(private readonly db: Db) {}

  async index(documentId: number) {
    if (this.indexError) throw this.indexError;
    this.indexed.push(documentId);
    if (this.finishIndexing) await this.db.query("UPDATE documents SET status = 'ready' WHERE id = $1", [documentId]);
  }

  async ask(input: { question: string; ownerId: string; documentIds: number[] }): Promise<Answer> {
    if (this.askError) throw this.askError;
    this.asked.push(input);
    return {
      answer: "It says so [1].",
      found: true,
      passages: input.documentIds.map((id, i) => ({ number: i + 1, document_id: id, name: `file${id}.md`, part: 1, text: `text ${id}`, score: 0.9, cited: i === 0 })),
    };
  }
}

export interface Result {
  status: number;
  json: any;
  text: string;
  headers: Headers;
}

export interface TestApp {
  db: Db;
  rag: FakeRag;
  config: Config;
  clock: { now: number };
  call(method: string, path: string, options?: { token?: string; internal?: boolean; body?: unknown; raw?: Buffer | string; headers?: Record<string, string> }): Promise<Result>;
  register(email: string, password?: string): Promise<{ id: string; token: string }>;
  tokenFor(userId: string): string;
  folder(token: string, name: string, parentId?: string): Promise<string>;
  upload(token: string, folderId: string, name: string, content?: string | Buffer): Promise<Result>;
  stop(): Promise<void>;
}

export async function startApp(overrides: Partial<Config> = {}): Promise<TestApp> {
  const database = await createTestDatabase();
  const uploadDir = await mkdtemp(path.join(os.tmpdir(), "docs-assistant-uploads-"));
  const config: Config = {
    port: 0,
    databaseUrl: "unused",
    ...SECRETS,
    ragServiceUrl: "http://unused",
    uploadDir,
    maxUploadBytes: 1024 * 1024,
    maxFilesPerUser: 1000,
    ...overrides,
  };
  const rag = new FakeRag(database.db);
  const clock = { now: Date.now() };
  const server = http.createServer(createApp({ config, db: database.db, rag, now: () => clock.now }));
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

  const tokenFor = (userId: string) => signToken(userId, config.apiJwtSecret, 60, () => clock.now);

  const app: TestApp = {
    db: database.db,
    rag,
    config,
    clock,
    tokenFor,
    async call(method, requestPath, options = {}) {
      const headers: Record<string, string> = { ...options.headers };
      if (options.token) headers.authorization = `Bearer ${options.token}`;
      if (options.internal) headers["x-internal-secret"] = config.internalSecret;
      let body: BodyInit | undefined;
      if (options.body !== undefined) {
        body = JSON.stringify(options.body);
        headers["content-type"] = "application/json";
      } else if (options.raw !== undefined) {
        body = options.raw as BodyInit;
      }
      const response = await fetch(base + requestPath, { method, headers, body });
      const text = await response.text();
      let parsed: any = null;
      try {
        parsed = text ? JSON.parse(text) : null;
      } catch {
        /* not JSON */
      }
      return { status: response.status, json: parsed, text, headers: response.headers };
    },
    async register(email, password = "correct horse battery") {
      const created = await app.call("POST", "/internal/register", { internal: true, body: { email, password } });
      if (created.status !== 201) throw new Error(`register failed: ${created.text}`);
      return { id: created.json.id, token: tokenFor(created.json.id) };
    },
    async folder(token, name, parentId) {
      const created = await app.call("POST", "/api/folders", { token, body: { name, parentId } });
      if (created.status !== 201) throw new Error(`folder failed: ${created.text}`);
      return created.json.folder.id;
    },
    upload(token, folderId, name, content = "Some text to search.") {
      return app.call("POST", `/api/folders/${folderId}/files?name=${encodeURIComponent(name)}`, { token, raw: content });
    },
    async stop() {
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
      await database.close();
      await rm(uploadDir, { recursive: true, force: true });
    },
  };
  return app;
}
