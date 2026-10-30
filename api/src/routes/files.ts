import { createHash } from "node:crypto";

import { isUniqueViolation, type Db } from "../db.js";
import { HttpError, notFound } from "../errors.js";
import { json, requireUser, type Ctx, type Reply, type RouteSpec } from "../http.js";
import type { RagClient } from "../ragClient.js";
import { readUpload, removeUploads, saveUpload } from "../storage.js";
import { countFiles, deleteFile, getFile, insertFile, markFailed, type FileRow } from "../store/files.js";
import { getFolder } from "../store/folders.js";
import { cleanFileName, parseId, parseUuid } from "../validate.js";

export const fileJson = (row: FileRow) => ({
  id: row.id,
  name: row.name,
  folderId: row.folder_id,
  status: row.status,
  error: row.error,
  sizeBytes: row.size_bytes === null ? null : Number(row.size_bytes),
  createdAt: row.created_at,
});

export interface UploadLimits {
  uploadDir: string;
  maxUploadBytes: number;
  maxFilesPerUser: number;
}

export function fileRoutes(db: Db, rag: RagClient, limits: UploadLimits): RouteSpec[] {
  async function ownedFile(ctx: Ctx): Promise<FileRow> {
    const file = await getFile(db, requireUser(ctx), parseId(ctx.params.id, "File"));
    if (!file) throw notFound("File");
    return file;
  }

  return [
    {
      // The request body is the raw file and the name comes from ?name= (so there is no multipart format to parse).
      method: "POST",
      path: "/api/folders/:id/files",
      auth: "user",
      async handle(ctx) {
        const userId = requireUser(ctx);
        const folderId = parseUuid(ctx.params.id, "Folder");
        if (!(await getFolder(db, userId, folderId))) throw notFound("Folder");
        const { name, extension } = cleanFileName(ctx.url.searchParams.get("name"));
        if ((await countFiles(db, userId)) >= limits.maxFilesPerUser) {
          throw new HttpError(409, "quota", `You can keep up to ${limits.maxFilesPerUser} files. Delete some first.`);
        }

        const bytes = await ctx.readBytes(limits.maxUploadBytes);
        if (bytes.length === 0) throw new HttpError(400, "empty_file", "The file is empty.");
        if (extension === ".pdf") {
          // A real PDF starts with "%PDF-" (the PDF spec allows a little junk before it, so look in the first 1024 bytes).
          if (!bytes.subarray(0, 1024).includes("%PDF-")) throw new HttpError(415, "not_pdf", "This file is not a valid PDF.");
        } else {
          if (bytes.toString("utf8").trim() === "") throw new HttpError(400, "empty_file", "The file is empty.");
          if (bytes.includes(0)) throw new HttpError(415, "not_text", "This looks like a binary file. Upload plain text (.md or .txt).");
        }

        const storagePath = await saveUpload(limits.uploadDir, userId, extension, bytes);
        let row: FileRow;
        try {
          row = await insertFile(db, {
            ownerId: userId,
            folderId,
            name,
            hash: createHash("sha256").update(bytes).digest("hex"),
            sizeBytes: bytes.length,
            storagePath,
          });
        } catch (error) {
          await removeUploads(limits.uploadDir, [storagePath]);
          if (isUniqueViolation(error)) throw new HttpError(409, "name_taken", "A file with this name already exists in this folder.");
          throw error;
        }

        // Hand the file to the indexing service. It answers at once and indexes in the background.
        try {
          await rag.index(row.id);
        } catch (error) {
          const message = error instanceof HttpError ? error.message : "The indexing service could not be reached.";
          await markFailed(db, row.id, message);
          row = { ...row, status: "failed", error: message };
        }
        return json(202, { file: fileJson(row) });
      },
    },
    {
      // Used by the website to see when "processing" turns into "ready".
      method: "GET",
      path: "/api/files/:id",
      auth: "user",
      async handle(ctx) {
        return json(200, { file: fileJson(await ownedFile(ctx)) });
      },
    },
    {
      method: "GET",
      path: "/api/files/:id/content",
      auth: "user",
      async handle(ctx): Promise<Reply> {
        const file = await ownedFile(ctx);
        if (!file.storage_path) throw notFound("File");
        let bytes: Buffer;
        try {
          bytes = await readUpload(limits.uploadDir, file.storage_path);
        } catch {
          throw notFound("File");
        }
        if (file.name.toLowerCase().endsWith(".pdf")) {
          return { status: 200, raw: bytes, headers: { "content-type": "application/pdf", "content-disposition": "inline" } };
        }
        return { status: 200, text: bytes.toString("utf8"), headers: { "content-type": "text/plain; charset=utf-8" } };
      },
    },
    {
      method: "DELETE",
      path: "/api/files/:id",
      auth: "user",
      async handle(ctx) {
        const removed = await deleteFile(db, requireUser(ctx), parseId(ctx.params.id, "File"));
        if (!removed) throw notFound("File");
        if (removed.storagePath) await removeUploads(limits.uploadDir, [removed.storagePath]);
        return json(204);
      },
    },
  ];
}
