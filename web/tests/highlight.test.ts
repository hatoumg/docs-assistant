import assert from "node:assert/strict";
import { test } from "node:test";

import { findPassage, matchParts } from "../lib/highlight.ts";

const doc = "# Terms\n\nThe notice period is\n30 days for both sides.\n\nFees are due monthly.";

test("finds a passage in a text file even when line breaks and spacing differ", () => {
  const match = findPassage([doc], "The notice period is 30 days   for both sides.")!;
  const [part] = matchParts([doc], match);
  assert.equal(doc.slice(part!.from, part!.to), "The notice period is\n30 days for both sides.");
});

test("finds a passage that runs across several PDF fragments, ignoring capitals and ligatures", () => {
  const pieces = ["Notice ", "period is 30", " days. Con", "ﬁdential", " terms apply."];
  const match = findPassage(pieces, "NOTICE PERIOD is 30 days. Confidential terms")!;
  const parts = matchParts(pieces, match);
  assert.deepEqual(parts.map((p) => p.piece), [0, 1, 2, 3, 4]);
  assert.deepEqual(parts[4], { piece: 4, from: 0, to: 6 });
  assert.deepEqual(parts[0], { piece: 0, from: 0, to: 7 });
});

test("still finds it when a line was hyphenated in one version and not the other", () => {
  const pieces = ["The agree-", "ment lasts for twelve months and renews every year unless either side gives written notice."];
  const match = findPassage(pieces, "The agreement lasts for twelve months and renews every year unless either side gives written notice.")!;
  assert.ok(match);
  assert.equal(match.start.piece, 0);
  assert.equal(match.end.piece, 1);
});

test("returns nothing when the passage is not there, or is too short to be meaningful", () => {
  assert.equal(findPassage([doc], "completely different words about something else"), null);
  assert.equal(findPassage([doc], "the"), null);
});
