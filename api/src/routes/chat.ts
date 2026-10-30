import type { Db } from "../db.js";
import { HttpError, notFound } from "../errors.js";
import { asObject, json, requireUser, type RouteSpec } from "../http.js";
import type { RagClient } from "../ragClient.js";
import { RateLimiter } from "../limits.js";
import { foldersOf, searchableScope } from "../store/files.js";
import { getFolder } from "../store/folders.js";
import { cleanQuestion, parseUuid } from "../validate.js";

const NOTHING_TO_SEARCH = "There are no indexed files here yet. Upload a .md or .txt file to this folder (or one inside it) and wait until it says Ready.";

export function chatRoutes(db: Db, rag: RagClient, chatLimiter: RateLimiter): RouteSpec[] {
  return [
    {
      // folderId = the folder the user is looking at. The answer may use that folder and everything below it.
      // No folderId (the top level) means all of the user's files.
      method: "POST",
      path: "/api/chat",
      auth: "user",
      async handle(ctx) {
        const userId = requireUser(ctx);
        const body = asObject(await ctx.readJson());
        const question = cleanQuestion(body.question);
        let folderId: string | null = null;
        if (body.folderId !== undefined && body.folderId !== null) {
          folderId = parseUuid(body.folderId, "Folder");
          if (!(await getFolder(db, userId, folderId))) throw notFound("Folder");
        }
        if (!chatLimiter.take(userId)) {
          throw new HttpError(429, "slow_down", "You are asking too fast. Wait a moment and try again.");
        }

        const scope = await searchableScope(db, userId, folderId);
        const searched = { files: scope.ready.length, processing: scope.pending, failed: scope.failed };
        if (scope.ready.length === 0) {
          return json(200, { answer: NOTHING_TO_SEARCH, found: false, passages: [], searched });
        }

        const result = await rag.ask({ question, ownerId: userId, documentIds: scope.ready });
        const folders = await foldersOf(db, userId, [...new Set(result.passages.map((p) => p.document_id))]);
        const passages = result.passages.map((p) => ({
          number: p.number,
          fileId: p.document_id,
          folderId: folders.get(p.document_id) ?? null,
          name: p.name,
          part: p.part,
          text: p.text,
          score: p.score,
          cited: p.cited,
        }));
        return json(200, { answer: result.answer, found: result.found, passages, searched });
      },
    },
  ];
}
