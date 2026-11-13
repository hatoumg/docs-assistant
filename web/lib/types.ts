/** The shapes the API returns. Kept in one place so the screens and the API client agree. */

export interface FolderItem {
  id: string;
  name: string;
  parentId: string | null;
  createdAt: string;
}

export type FileStatus = "processing" | "ready" | "failed";

/** The kinds of document a user can pick when uploading. The type chooses how the file is cut into passages for search.
 * Keep the values in step with DOC_TYPES in api/src/validate.ts and worker/1_indexing/3_chunk.py. */
export const DOC_TYPES = [
  { value: "auto", label: "Let the app decide" },
  { value: "general", label: "General text" },
  { value: "technical", label: "Technical docs" },
  { value: "report", label: "Report" },
  { value: "paper", label: "Research paper" },
  { value: "contract", label: "Contract" },
  { value: "legal", label: "Legal text" },
  { value: "policy", label: "Policy" },
] as const;
export type DocType = (typeof DOC_TYPES)[number]["value"];

export const docTypeLabel = (value: string | null) => DOC_TYPES.find((t) => t.value === value)?.label ?? null;

export interface FileItem {
  id: number;
  name: string;
  folderId: string;
  status: FileStatus;
  error: string | null;
  sizeBytes: number | null;
  docType: string | null; // null when the user let the app decide
  createdAt: string;
}

export interface Listing {
  folder: FolderItem | null;
  breadcrumbs: { id: string; name: string }[];
  folders: FolderItem[];
  files: FileItem[];
}

export interface Passage {
  number: number;
  fileId: number;
  folderId: string | null;
  name: string;
  part: number;
  text: string;
  score: number;
  cited: boolean;
}

export interface ChatResult {
  answer: string;
  found: boolean;
  passages: Passage[];
  searched: { files: number; processing: number; failed: number };
}
