import { isUniqueViolation, type Db } from "../db.js";
import { HttpError, notFound } from "../errors.js";
import { asObject, json, requireUser, type RouteSpec } from "../http.js";
import { removeUploads } from "../storage.js";
import { breadcrumbs, createFolder, deleteFolder, getFolder, listChildren, type FolderRow } from "../store/folders.js";
import { listFiles } from "../store/files.js";
import { cleanName, parseUuid } from "../validate.js";
import { fileJson } from "./files.js";

const folderJson = (row: FolderRow) => ({ id: row.id, name: row.name, parentId: row.parent_id, createdAt: row.created_at });

export function folderRoutes(db: Db, uploadDir: string): RouteSpec[] {
  return [
    {
      // The contents of one folder (or the top level when ?parent= is left out).
      method: "GET",
      path: "/api/folders",
      auth: "user",
      async handle(ctx) {
        const userId = requireUser(ctx);
        const parent = ctx.url.searchParams.get("parent");
        if (parent === null) {
          return json(200, { folder: null, breadcrumbs: [], folders: (await listChildren(db, userId, null)).map(folderJson), files: [] });
        }
        const id = parseUuid(parent, "Folder");
        const folder = await getFolder(db, userId, id);
        if (!folder) throw notFound("Folder");
        const [trail, children, files] = await Promise.all([
          breadcrumbs(db, userId, id),
          listChildren(db, userId, id),
          listFiles(db, userId, id),
        ]);
        return json(200, { folder: folderJson(folder), breadcrumbs: trail, folders: children.map(folderJson), files: files.map(fileJson) });
      },
    },
    {
      method: "POST",
      path: "/api/folders",
      auth: "user",
      async handle(ctx) {
        const userId = requireUser(ctx);
        const body = asObject(await ctx.readJson());
        const name = cleanName(body.name, "Folder name");
        let parentId: string | null = null;
        if (body.parentId !== undefined && body.parentId !== null) {
          parentId = parseUuid(body.parentId, "Parent folder");
          if (!(await getFolder(db, userId, parentId))) throw notFound("Parent folder");
        }
        try {
          return json(201, { folder: folderJson(await createFolder(db, userId, parentId, name)) });
        } catch (error) {
          if (isUniqueViolation(error)) throw new HttpError(409, "name_taken", "A folder with this name already exists here.");
          throw error;
        }
      },
    },
    {
      method: "DELETE",
      path: "/api/folders/:id",
      auth: "user",
      async handle(ctx) {
        const userId = requireUser(ctx);
        const paths = await deleteFolder(db, userId, parseUuid(ctx.params.id, "Folder"));
        if (paths === null) throw notFound("Folder");
        await removeUploads(uploadDir, paths);
        return json(204);
      },
    },
  ];
}
