/** Turns "It is 30 days [1][2]." into pieces, so the screen can show [1] and [2] as clickable chips. */

export type AnswerPart = { type: "text"; text: string } | { type: "cite"; number: number };

export function splitAnswer(answer: string): AnswerPart[] {
  // Some models write 【1】 instead of [1]; treat them the same.
  const normalised = answer.replace(/[【［]\s*(\d+)\s*[】］]/g, "[$1]");
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of normalised.matchAll(/\[(\d{1,3})\]/g)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ type: "text", text: normalised.slice(last, start) });
    parts.push({ type: "cite", number: Number(match[1]) });
    last = start + match[0].length;
  }
  if (last < normalised.length) parts.push({ type: "text", text: normalised.slice(last) });
  return parts;
}

/** Only numbers that point at a real passage become chips; others stay as plain text. */
export function linkCitations(parts: AnswerPart[], passageCount: number): AnswerPart[] {
  return parts.map((part) =>
    part.type === "cite" && (part.number < 1 || part.number > passageCount) ? { type: "text", text: `[${part.number}]` } : part,
  );
}
