"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { askQuestion } from "@/lib/api";
import { linkCitations, splitAnswer } from "@/lib/citations";
import { scopeText } from "@/lib/format";
import type { ChatResult } from "@/lib/types";
import { useScope } from "./Scope";

interface Turn {
  question: string;
  scopeLabel: string;
  result?: ChatResult;
  error?: string;
}

/** The chat. It always searches the folder you are in now, and every folder inside it. */
export function Chat() {
  const { scope } = useScope();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false); // phones only: the chat is a sheet
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns, open]);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const question = text.trim();
    if (!question || busy) return;
    const index = turns.length;
    const scopeLabel = scopeText(scope.folderId ? scope.name ?? "this folder" : null);
    setTurns((all) => [...all, { question, scopeLabel }]);
    setText("");
    setBusy(true);
    try {
      const result = await askQuestion(question, scope.folderId);
      setTurns((all) => all.map((t, i) => (i === index ? { ...t, result } : t)));
    } catch (e) {
      setTurns((all) => all.map((t, i) => (i === index ? { ...t, error: (e as Error).message } : t)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="chat-fab btn primary" onClick={() => setOpen(true)}>Ask a question</button>
      <aside className={`chat ${open ? "open" : ""}`} aria-label="Chat">
        <div className="chat-head">
          <div>
            <strong>Ask your files</strong>
            <div className="scope">Searching {scopeText(scope.folderId ? scope.name ?? "this folder" : null)}</div>
          </div>
          <button className="btn small chat-close" onClick={() => setOpen(false)}>Close</button>
        </div>
        <div className="chat-log">
          {turns.length === 0 && <p className="muted">Ask anything about the files in this folder. Answers show which passages they came from.</p>}
          {turns.map((turn, i) => (
            <div key={i} className="turn">
              <div className="bubble user">{turn.question}</div>
              {turn.error ? (
                <p className="error">{turn.error}</p>
              ) : !turn.result ? (
                <p className="muted">Thinking…</p>
              ) : (
                <Answer result={turn.result} />
              )}
            </div>
          ))}
          <div ref={end} />
        </div>
        <form className="chat-form" onSubmit={send}>
          <textarea
            value={text}
            maxLength={2000}
            rows={2}
            placeholder="Ask a question…"
            aria-label="Your question"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) send(e);
            }}
          />
          <button className="btn primary" type="submit" disabled={busy || !text.trim()}>Send</button>
        </form>
      </aside>
    </>
  );
}

function Answer({ result }: { result: ChatResult }) {
  const [shown, setShown] = useState<number | null>(null);
  const parts = linkCitations(splitAnswer(result.answer), result.passages.length);
  const cited = result.passages.filter((p) => p.cited);
  const sources = cited.length > 0 ? cited : [];
  const { searched } = result;
  return (
    <div className="bubble bot">
      <p className="answer">
        {parts.map((part, i) =>
          part.type === "text" ? (
            <span key={i}>{part.text}</span>
          ) : (
            <button key={i} className="chip" onClick={() => setShown(shown === part.number ? null : part.number)} aria-label={`Passage ${part.number}`}>
              {part.number}
            </button>
          ),
        )}
      </p>
      {shown !== null && result.passages[shown - 1] && <Passage passage={result.passages[shown - 1]!} />}
      {sources.length > 0 && shown === null && (
        <details className="sources">
          <summary>{sources.length} source{sources.length === 1 ? "" : "s"}</summary>
          {sources.map((p) => <Passage key={p.number} passage={p} />)}
        </details>
      )}
      {searched.files === 0 && <p className="muted small">There are no ready files in this folder yet.</p>}
      {(searched.processing > 0 || searched.failed > 0) && (
        <p className="muted small">
          {searched.processing > 0 && `${searched.processing} file(s) are still being read. `}
          {searched.failed > 0 && `${searched.failed} file(s) could not be read and were skipped.`}
        </p>
      )}
    </div>
  );
}

function Passage({ passage }: { passage: ChatResult["passages"][number] }) {
  const router = useRouter();
  const { scope, setHighlight } = useScope();
  function show() {
    setHighlight({ fileId: passage.fileId, text: passage.text, key: Date.now() });
    if (passage.folderId && passage.folderId !== scope.folderId) router.push(`/folder/${passage.folderId}`);
  }
  return (
    <blockquote className="passage">
      <div className="passage-head">
        <span className="chip static">{passage.number}</span>
        {passage.name}
        <span className="muted small"> · part {passage.part}</span>
      </div>
      <div>{passage.text}</div>
      <button className="btn small" onClick={show}>Show in document</button>
    </blockquote>
  );
}
