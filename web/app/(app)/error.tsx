"use client";

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  console.error("Page error:", error);
  return (
    <section className="panel">
      <p className="error">Something went wrong.</p>
      {error.message && <pre className="file-text small">{error.message}</pre>}
      <button className="btn" onClick={reset}>Try again</button>
    </section>
  );
}
