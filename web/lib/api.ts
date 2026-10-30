import type { ChatResult, FileItem, FolderItem, Listing } from "./types";

/** Calls from the browser. They go to the website's own /backend proxy, which adds the sign-in token. */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/backend/${path}`, { ...init, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Could not reach the website. Check your connection.");
  }
  if (response.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "Please sign in again.");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data?.message ?? "Something went wrong.");
  return data as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const listFolder = (id: string | null) => call<Listing>(id ? `folders?parent=${encodeURIComponent(id)}` : "folders");
export const createFolder = (name: string, parentId: string | null) =>
  call<{ folder: FolderItem }>("folders", json("POST", { name, parentId }));
export const deleteFolder = (id: string) => call<void>(`folders/${id}`, { method: "DELETE" });
export const uploadFile = (folderId: string, file: File) =>
  call<{ file: FileItem }>(`folders/${folderId}/files?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "content-type": "application/octet-stream" },
    body: file,
  });
export const deleteFile = (id: number) => call<void>(`files/${id}`, { method: "DELETE" });
export async function fileText(id: number): Promise<string> {
  const response = await fetch(`/backend/files/${id}/content`, { cache: "no-store" });
  if (!response.ok) throw new ApiError(response.status, "Could not open this file.");
  return response.text();
}
export const askQuestion = (question: string, folderId: string | null) =>
  call<ChatResult>("chat", json("POST", folderId ? { question, folderId } : { question }));
