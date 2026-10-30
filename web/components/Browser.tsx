"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { createFolder, deleteFile, deleteFolder, listFolder, uploadFile } from "@/lib/api";
import { formatDate, formatSize } from "@/lib/format";
import type { FileItem, Listing } from "@/lib/types";
import { FilePreview } from "./FilePreview";
import { useScope } from "./Scope";

/** The folder screen: the path at the top, then the folders and files inside the current folder. */
export function Browser({ folderId, openFileId }: { folderId: string | null; openFileId: number | null }) {
  const { setScope, highlight, setHighlight } = useScope();
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null); // "folder:<id>" or "file:<id>"
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<{ file: FileItem; highlight?: string } | null>(null);
  const handledHighlight = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setListing(await listFolder(folderId));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, [folderId]);

  useEffect(() => {
    setListing(null);
    setCreating(false);
    setConfirm(null);
    setNotice("");
    load();
  }, [load]);

  useEffect(() => {
    setScope({ folderId, name: listing?.folder?.name ?? null });
  }, [folderId, listing?.folder?.name, setScope]);

  // While a file is still being read by the model, check again every 2 seconds.
  const waiting = listing?.files.some((f) => f.status === "processing") ?? false;
  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [waiting, load]);

  useEffect(() => {
    if (openFileId === null || !listing) return;
    const file = listing.files.find((f) => f.id === openFileId);
    if (file) setPreview((current) => (current?.file.id === file.id ? current : { file }));
  }, [openFileId, listing]);

  // The chat asked to see a passage: open its file with the passage highlighted (once per click).
  useEffect(() => {
    if (!highlight || !listing || handledHighlight.current === highlight.key) return;
    const file = listing.files.find((f) => f.id === highlight.fileId);
    if (!file) return;
    handledHighlight.current = highlight.key;
    setPreview({ file, highlight: highlight.text });
    setHighlight(null); // used up, so closing the file or an error never reopens it
  }, [highlight, listing, setHighlight]);

  async function submitFolder(event: React.FormEvent) {
    event.preventDefault();
    if (!newName.trim()) return;
    try {
      await createFolder(newName.trim(), folderId);
      setNewName("");
      setCreating(false);
      setError("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function onFiles(files: FileList | null) {
    if (!files || files.length === 0 || !folderId) return;
    setUploading(true);
    const problems: string[] = [];
    for (const file of Array.from(files)) {
      try {
        await uploadFile(folderId, file);
      } catch (e) {
        problems.push(`${file.name}: ${(e as Error).message}`);
      }
    }
    if (fileInput.current) fileInput.current.value = "";
    setUploading(false);
    setNotice(problems.join("\n"));
    await load();
  }

  async function remove(kind: "folder" | "file", id: string | number) {
    try {
      if (kind === "folder") await deleteFolder(String(id));
      else await deleteFile(Number(id));
      setConfirm(null);
      setError("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!listing) return <section className="panel">{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</section>;

  const empty = listing.folders.length === 0 && listing.files.length === 0;
  const confirmBox = (kind: "folder" | "file", id: string | number, what: string) =>
    confirm === `${kind}:${id}` ? (
      <span className="confirm">
        {what}
        <button className="btn small danger" onClick={() => remove(kind, id)}>Delete</button>
        <button className="btn small" onClick={() => setConfirm(null)}>Cancel</button>
      </span>
    ) : (
      <button className="btn small ghost" aria-label={`Delete ${kind}`} onClick={() => setConfirm(`${kind}:${id}`)}>Delete</button>
    );

  return (
    <section className="panel">
      <nav className="crumbs" aria-label="Path">
        <Link href="/">All folders</Link>
        {listing.breadcrumbs.map((crumb, i) => (
          <span key={crumb.id}>
            <span className="sep">/</span>
            {i === listing.breadcrumbs.length - 1 ? <strong>{crumb.name}</strong> : <Link href={`/folder/${crumb.id}`}>{crumb.name}</Link>}
          </span>
        ))}
      </nav>

      <div className="toolbar">
        <h1>{listing.folder?.name ?? "Your folders"}</h1>
        <div className="actions">
          <button className="btn" onClick={() => setCreating((v) => !v)}>New folder</button>
          {folderId && (
            <>
              <button className="btn primary" disabled={uploading} onClick={() => fileInput.current?.click()}>
                {uploading ? "Uploading…" : "Upload files"}
              </button>
              <input ref={fileInput} type="file" multiple accept=".md,.txt,.pdf,text/plain,text/markdown,application/pdf" hidden onChange={(e) => onFiles(e.target.files)} />
            </>
          )}
        </div>
      </div>

      {creating && (
        <form className="inline-form" onSubmit={submitFolder}>
          <input autoFocus value={newName} maxLength={120} onChange={(e) => setNewName(e.target.value)} placeholder="Folder name" aria-label="Folder name" />
          <button className="btn primary" type="submit">Create</button>
          <button className="btn" type="button" onClick={() => setCreating(false)}>Cancel</button>
        </form>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="error" role="alert" style={{ whiteSpace: "pre-line" }}>{notice}</p>}

      {empty ? (
        <p className="muted empty">
          {folderId ? "This folder is empty. Create a folder inside it or upload .md, .txt or .pdf files." : "No folders yet. Create one to get started, then upload files into it."}
        </p>
      ) : (
        <ul className="rows">
          {listing.folders.map((folder) => (
            <li key={folder.id} className="row">
              <Link className="row-main" href={`/folder/${folder.id}`}>
                <span className="icon" aria-hidden>📁</span>
                <span className="name">{folder.name}</span>
                <span className="meta">{formatDate(folder.createdAt)}</span>
              </Link>
              {confirmBox("folder", folder.id, "Delete it and everything inside? ")}
            </li>
          ))}
          {listing.files.map((file) => (
            <li key={file.id} className="row">
              <button className="row-main" onClick={() => setPreview({ file })} disabled={file.status === "failed"}>
                <span className="icon" aria-hidden>📄</span>
                <span className="name">{file.name}</span>
                <span className="meta">{formatSize(file.sizeBytes)}</span>
                <span className={`badge ${file.status}`}>
                  {file.status === "processing" ? "Reading…" : file.status === "ready" ? "Ready" : "Failed"}
                </span>
              </button>
              {confirmBox("file", file.id, "Delete this file? ")}
              {file.status === "failed" && file.error && <p className="error row-error">{file.error}</p>}
            </li>
          ))}
        </ul>
      )}

      {preview && <FilePreview fileId={preview.file.id} name={preview.file.name} highlight={preview.highlight} onClose={() => setPreview(null)} />}
    </section>
  );
}
