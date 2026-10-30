import { randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

/** Uploaded files live on disk under one folder, in a sub-folder per user, with random names. */

function resolveInside(root: string, relative: string): string {
  const full = path.resolve(root, relative);
  if (!full.startsWith(path.resolve(root) + path.sep)) throw new Error("path escapes the upload folder");
  return full;
}

/** Saves the bytes and returns the path relative to the upload folder (that is what the database stores). */
export async function saveUpload(root: string, ownerId: string, extension: string, bytes: Buffer): Promise<string> {
  const relative = `${ownerId}/${randomUUID()}${extension}`;
  const full = resolveInside(root, relative);
  await mkdir(path.dirname(full), { recursive: true });
  await writeFile(full, bytes, { flag: "wx" });
  return relative;
}

export async function readUpload(root: string, relative: string): Promise<Buffer> {
  return readFile(resolveInside(root, relative));
}

/** Best effort: a missing file is not an error. */
export async function removeUploads(root: string, relatives: string[]): Promise<void> {
  await Promise.all(
    relatives.map(async (relative) => {
      try {
        await rm(resolveInside(root, relative), { force: true });
      } catch (error) {
        console.error("Could not remove an uploaded file:", relative, error);
      }
    }),
  );
}
