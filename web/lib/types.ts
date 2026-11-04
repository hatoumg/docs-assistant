/** The shapes the API returns. Kept in one place so the screens and the API client agree. */

export interface FolderItem {
  id: string;
  name: string;
  parentId: string | null;
  createdAt: string;
}

export type FileStatus = "processing" | "ready" | "failed";

export interface FileItem {
  id: number;
  name: string;
  folderId: string;
  status: FileStatus;
  error: string | null;
  sizeBytes: number | null;
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
