import { HttpError } from "./errors.js";

export interface Passage {
  number: number;
  document_id: number;
  name: string;
  part: number;
  text: string;
  score: number;
  cited: boolean;
}

export interface Answer {
  answer: string;
  found: boolean;
  passages: Passage[];
}

/** What the API needs from the Python service. Tests replace it with a fake. */
export interface RagClient {
  index(documentId: number): Promise<void>;
  ask(input: { question: string; ownerId: string; documentIds: number[] }): Promise<Answer>;
}

export function createRagClient(baseUrl: string, secret: string, fetchImpl: typeof fetch = fetch): RagClient {
  async function post(path: string, body: unknown, timeoutMs: number): Promise<Response> {
    try {
      return await fetchImpl(`${baseUrl}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-internal-secret": secret },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch {
      throw new HttpError(502, "rag_unavailable", "The answering service is not reachable. Is it running?");
    }
  }

  return {
    async index(documentId) {
      const response = await post("/index", { document_id: documentId }, 10_000);
      if (!response.ok) throw new HttpError(502, "rag_unavailable", `The indexing service refused the file (HTTP ${response.status}).`);
    },

    async ask({ question, ownerId, documentIds }) {
      const response = await post("/ask", { question, owner_id: ownerId, document_ids: documentIds }, 120_000);
      const data = (await response.json().catch(() => null)) as (Partial<Answer> & { error?: string }) | null;
      if (!response.ok || !data || typeof data.answer !== "string" || !Array.isArray(data.passages)) {
        throw new HttpError(502, "rag_failed", data?.error ?? "The answering service returned an unexpected reply.");
      }
      return { answer: data.answer, found: Boolean(data.found), passages: data.passages };
    },
  };
}
