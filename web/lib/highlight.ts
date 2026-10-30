/**
 * Finds a passage inside a document so the screen can highlight it.
 *
 * The document is given as pieces in reading order (one piece for a text file; one per text fragment for a PDF page).
 * The passage came from our own text extraction, which can differ from what is on screen in spacing, line breaks,
 * capital letters, hyphens at line ends and ligatures (ﬁ). So both sides are compared with whitespace and hyphens removed
 * and letters lower-cased.
 */
export interface Position {
  piece: number; // which piece
  offset: number; // character offset inside that piece
}
export interface Match {
  start: Position;
  end: Position; // just after the last matched character
}

interface Stream {
  text: string;
  piece: number[];
  offset: number[];
}

function toStream(pieces: string[]): Stream {
  const stream: Stream = { text: "", piece: [], offset: [] };
  pieces.forEach((piece, p) => {
    let offset = 0;
    for (const char of piece) {
      for (const c of char.normalize("NFKC").toLowerCase()) {
        if (!/[\s\-\u00ad\u2010\u2011]/.test(c)) {
          stream.text += c;
          stream.piece.push(p);
          stream.offset.push(offset);
        }
      }
      offset += char.length;
    }
  });
  return stream;
}

const normalise = (text: string) => toStream([text]).text;

/** How much of the start and end to match when the whole passage cannot be found exactly. */
const EDGE = 40;

export function findPassage(pieces: string[], passage: string): Match | null {
  const needle = normalise(passage);
  if (needle.length < 8) return null;
  const hay = toStream(pieces);

  let from = hay.text.indexOf(needle);
  let to = from + needle.length;
  if (from < 0) {
    // Something inside differs (a removed header, a changed word). Find the start and the end separately.
    const head = needle.slice(0, EDGE);
    const tail = needle.slice(-EDGE);
    from = hay.text.indexOf(head);
    if (from < 0) return null;
    const tailAt = hay.text.indexOf(tail, from + head.length - 1);
    to = tailAt >= 0 && tailAt + tail.length - from <= needle.length * 2 ? tailAt + tail.length : Math.min(hay.text.length, from + needle.length);
  }
  const last = to - 1;
  return {
    start: { piece: hay.piece[from]!, offset: hay.offset[from]! },
    end: { piece: hay.piece[last]!, offset: hay.offset[last]! + 1 },
  };
}

/** The pieces a match touches, each with the part of it that is highlighted. */
export function matchParts(pieces: string[], match: Match): { piece: number; from: number; to: number }[] {
  const parts: { piece: number; from: number; to: number }[] = [];
  for (let p = match.start.piece; p <= match.end.piece; p++) {
    const length = pieces[p]?.length ?? 0;
    const from = p === match.start.piece ? match.start.offset : 0;
    const to = p === match.end.piece ? match.end.offset : length;
    if (to > from) parts.push({ piece: p, from, to });
  }
  return parts;
}
