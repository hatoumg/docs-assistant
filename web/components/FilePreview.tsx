"use client";

import { Component, useEffect, useRef, useState, type ReactNode } from "react";

import { fileText } from "@/lib/api";
import { findPassage, matchParts } from "@/lib/highlight";
import { PdfViewer, type ViewerStatus } from "./PdfViewer";

/**
 * Opens a file. If `highlight` is given (the text of a passage the chat used), that passage is marked and scrolled into view,
 * on the real PDF page for a PDF and in the text for a .md or .txt file.
 */
export function FilePreview({ fileId, name, highlight, onClose }: { fileId: number; name: string; highlight?: string; onClose: () => void }) {
  const isPdf = name.toLowerCase().endsWith(".pdf");
  const [status, setStatus] = useState<ViewerStatus>({ state: "loading" });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="overlay" onClick={onClose}>
      <div className={`dialog ${isPdf ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={name} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <strong>{name}</strong>
          <span className="dialog-actions">
            {isPdf && <a className="small" href={`/backend/files/${fileId}/content`} target="_blank" rel="noopener">Open in a new tab</a>}
            <button className="btn small" onClick={onClose}>Close</button>
          </span>
        </div>
        {isPdf ? (
          <>
            <PdfNote status={status} asked={Boolean(highlight)} />
            <div className="pdf-scroll">
              <ViewerGuard>
                <PdfViewer fileId={fileId} highlight={highlight} onStatus={setStatus} />
              </ViewerGuard>
            </div>
          </>
        ) : (
          <TextViewer fileId={fileId} highlight={highlight} />
        )}
      </div>
    </div>
  );
}

/** If the PDF viewer crashes, show what happened here, not a blank page. */
class ViewerGuard extends Component<{ children: ReactNode }, { message: string | null }> {
  state = { message: null as string | null };
  static getDerivedStateFromError(error: Error) {
    return { message: error?.message || String(error) };
  }
  componentDidCatch(error: Error) {
    console.error("PDF viewer crashed:", error);
  }
  render() {
    if (this.state.message === null) return this.props.children;
    return (
      <div>
        <p className="error">The PDF viewer could not start.</p>
        <pre className="file-text small">{this.state.message}</pre>
        <p className="muted small">You can still use “Open in a new tab” above.</p>
      </div>
    );
  }
}

function PdfNote({ status, asked }: { status: ViewerStatus; asked: boolean }) {
  if (status.state === "error") return <p className="error">{status.message}</p>;
  if (status.state === "loading") return <p className="muted small">Loading…</p>;
  if (!asked) return null;
  return status.found ? (
    <p className="muted small">Highlighted the passage the answer used{status.page ? ` (page ${status.page})` : ""}.</p>
  ) : (
    <p className="muted small">Could not find the exact passage on the pages, so nothing is highlighted.</p>
  );
}

function TextViewer({ fileId, highlight }: { fileId: number; highlight?: string }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState("");
  const mark = useRef<HTMLElement>(null);

  useEffect(() => {
    let alive = true;
    setText(null);
    setError("");
    fileText(fileId).then(
      (value) => alive && setText(value),
      (e: Error) => alive && setError(e.message),
    );
    return () => {
      alive = false;
    };
  }, [fileId]);

  const match = text !== null && highlight ? findPassage([text], highlight) : null;
  const part = match && text !== null ? matchParts([text], match)[0] : undefined;

  useEffect(() => {
    mark.current?.scrollIntoView({ block: "center" });
  }, [text, highlight, part?.from]);

  if (error) return <p className="error">{error}</p>;
  if (text === null) return <p className="muted">Loading…</p>;
  return (
    <>
      {highlight && <p className="muted small">{part ? "Highlighted the passage the answer used." : "Could not find the exact passage, so nothing is highlighted."}</p>}
      <pre className="file-text">
        {part ? (
          <>
            {text.slice(0, part.from)}
            <mark ref={mark} className="hit">{text.slice(part.from, part.to)}</mark>
            {text.slice(part.to)}
          </>
        ) : (
          text
        )}
      </pre>
    </>
  );
}
