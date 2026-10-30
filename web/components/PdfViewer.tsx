"use client";

import "pdfjs-dist/web/pdf_viewer.css";

import { useEffect, useRef } from "react";

import { findPassage, matchParts } from "@/lib/highlight";
import { pdfWorkerUrl } from "@/lib/pdfWorker";

export type ViewerStatus =
  | { state: "loading" }
  | { state: "ready"; found: boolean | null; page: number | null } // found is null when no passage was asked for
  | { state: "error"; message: string };

interface PageState {
  number: number;
  wrapper: HTMLDivElement;
  page: any;
  viewport: any;
  textContent: any;
  firstPiece: number; // index of this page's first text fragment among all fragments in the document
  pieceCount: number;
  rendered: boolean;
}

/** Shows the real PDF pages. When `highlight` is given, the passage is marked in yellow and scrolled into view. */
export function PdfViewer({ fileId, highlight, onStatus }: { fileId: number; highlight?: string; onStatus: (status: ViewerStatus) => void }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let task: any = null;
    let observer: IntersectionObserver | null = null;
    const container = box.current!;
    container.replaceChildren();
    onStatus({ state: "loading" });

    (async () => {
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl();

      const response = await fetch(`/backend/files/${fileId}/content`, { cache: "no-store" });
      if (!response.ok) throw new Error("Could not open this PDF.");
      task = pdfjs.getDocument({ data: new Uint8Array(await response.arrayBuffer()) });
      const pdf = await task.promise;
      if (cancelled) return;

      // 1. Size every page and read its text (cheap). Drawing the pages comes later, only for the ones on screen.
      const width = Math.max(300, container.clientWidth - 2);
      const pages: PageState[] = [];
      const pieces: string[] = [];
      for (let number = 1; number <= pdf.numPages; number++) {
        const page = await pdf.getPage(number);
        const scale = width / page.getViewport({ scale: 1 }).width;
        const viewport = page.getViewport({ scale });
        const textContent = await page.getTextContent();
        const strings: string[] = textContent.items.filter((item: any) => typeof item.str === "string").map((item: any) => item.str);
        const wrapper = document.createElement("div");
        wrapper.className = "pdf-page";
        wrapper.style.width = `${Math.floor(viewport.width)}px`;
        wrapper.style.height = `${Math.floor(viewport.height)}px`;
        wrapper.style.setProperty("--scale-factor", String(scale));
        wrapper.style.setProperty("--total-scale-factor", String(scale));
        wrapper.dataset.page = String(number);
        container.appendChild(wrapper);
        pages.push({ number, wrapper, page, viewport, textContent, firstPiece: pieces.length, pieceCount: strings.length, rendered: false });
        pieces.push(...strings);
        if (cancelled) return;
      }

      // 2. Where is the passage?
      const match = highlight ? findPassage(pieces, highlight) : null;
      const parts = match ? matchParts(pieces, match) : [];
      const pageOf = (piece: number) => pages.find((p) => piece >= p.firstPiece && piece < p.firstPiece + p.pieceCount);
      const firstPage = parts.length > 0 ? pageOf(parts[0]!.piece) : undefined;
      onStatus({ state: "ready", found: highlight ? parts.length > 0 : null, page: firstPage?.number ?? null });

      // 3. Draw a page (picture + selectable text + yellow marks) when it comes near the screen.
      let scrolled = false;
      async function draw(p: PageState) {
        if (p.rendered || cancelled) return;
        p.rendered = true;
        const ratio = window.devicePixelRatio || 1;
        const canvas = document.createElement("canvas");
        canvas.width = Math.floor(p.viewport.width * ratio);
        canvas.height = Math.floor(p.viewport.height * ratio);
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        const hits = document.createElement("div");
        hits.className = "pdf-hits";
        const textLayer = document.createElement("div");
        textLayer.className = "textLayer";
        p.wrapper.append(canvas, hits, textLayer);

        await p.page.render({ canvasContext: canvas.getContext("2d")!, viewport: p.viewport, transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined }).promise;
        const layer = new pdfjs.TextLayer({ textContentSource: p.textContent, container: textLayer, viewport: p.viewport });
        await layer.render();
        if (cancelled) return;

        const mine = parts.filter((part) => part.piece >= p.firstPiece && part.piece < p.firstPiece + p.pieceCount);
        if (mine.length === 0 || layer.textDivs.length !== p.pieceCount) return;
        const origin = p.wrapper.getBoundingClientRect();
        for (const part of mine) {
          const node = layer.textDivs[part.piece - p.firstPiece]?.firstChild;
          if (!node) continue;
          const range = document.createRange();
          range.setStart(node, Math.min(part.from, node.textContent!.length));
          range.setEnd(node, Math.min(part.to, node.textContent!.length));
          for (const rect of Array.from(range.getClientRects())) {
            if (rect.width < 1 || rect.height < 1) continue;
            const mark = document.createElement("div");
            mark.className = "pdf-hit";
            mark.style.left = `${rect.left - origin.left}px`;
            mark.style.top = `${rect.top - origin.top}px`;
            mark.style.width = `${rect.width}px`;
            mark.style.height = `${rect.height}px`;
            hits.appendChild(mark);
          }
        }
        if (p === firstPage && !scrolled) {
          scrolled = true;
          hits.firstElementChild?.scrollIntoView({ block: "center" });
        }
      }

      observer = new IntersectionObserver(
        (entries) => entries.forEach((entry) => entry.isIntersecting && draw(pages[Number((entry.target as HTMLElement).dataset.page) - 1]!)),
        { root: container.parentElement, rootMargin: "800px 0px" },
      );
      pages.forEach((p) => observer!.observe(p.wrapper));
      if (firstPage) {
        // Jump to the page first, so it is drawn at once; the exact line is centred after it is drawn.
        container.parentElement!.scrollTop = firstPage.wrapper.offsetTop - 40;
        draw(firstPage);
      }
    })().catch((error: Error) => !cancelled && onStatus({ state: "error", message: error.message || "Could not open this PDF." }));

    return () => {
      cancelled = true;
      observer?.disconnect();
      // Free the PDF. Which object has destroy() differs between pdf.js versions, and cleanup must never throw.
      try {
        void task?.destroy?.();
      } catch {
        /* nothing to do */
      }
    };
    // onStatus is deliberately left out: the parent passes a new function every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, highlight]);

  return <div ref={box} className="pdf-pages" />;
}
