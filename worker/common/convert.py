"""Turns PDF and Word files into clean, standard text, so the rest of the pipeline sees the same kind of input.

The "standard text" is plain Markdown:

    # Heading                 headings start with # (## for a sub-heading, and so on)
    a paragraph               a blank line ends every paragraph; lines inside a paragraph are joined
    - a list item             list items are one per line
    | a | table |             tables become pipe tables, one row per line

Try it on a file and read the result:

    python -m common.convert ../storage/uploads/some-file.pdf
    python -m common.convert report.docx -o report.md

"""
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from markitdown import MarkItDown

CONVERTIBLE = (".pdf", ".docx")
CONVERTED_SUFFIX = ".converted.md"  # the converted text of an uploaded file is saved as <stored name>.converted.md


class ConversionError(ValueError):
    """The file could not be turned into text. The message is shown to the user on the file."""


@dataclass
class Converted:
    text: str
    # Where each PDF page starts: [(character position in text, page number)]. Used later to cite page numbers.
    page_starts: list = field(default_factory=list)


# ----- small helpers -----

_REPLACE = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", " ": " ", "​": "", "­": ""})
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_BULLET = re.compile(r"^\s*(?:[•◦▪▫‣∙●○■□·]|[-–—*](?=\s)|\d{1,3}[.)](?=\s)|\(?[a-zA-Z][.)](?=\s))\s*")
_SYMBOL_BULLET = re.compile(r"^\s*(?:[•◦▪▫‣∙●○■□·]|[-–—*](?=\s))")
_TERMINAL = re.compile(r"[.!?:;…”\"')\]]\s*$")
_PAGE_NUMBER = re.compile(r"^(page\s*)?#(\s*(of|/)\s*#)?$")


def _tidy(text):
    text = _CONTROL.sub("", text.translate(_REPLACE))
    return re.sub(r"[ \t]+", " ", text).strip()


def _join(previous, following):
    """Joins two lines of one paragraph. A word split by a hyphen at the line end is put back together."""
    if re.search(r"[A-Za-z]{2}-$", previous) and following[:1].islower():
        return previous[:-1] + following
    return previous + " " + following


def _pipe_table(rows):
    """Rows (lists of cell text) as a Markdown table. Empty tables give ''."""
    rows = [[_tidy((cell or "").replace("\n", " ")) for cell in row] for row in rows if row]
    width = max((len(row) for row in rows), default=0)
    cells = sum(1 for row in rows for cell in row if cell)
    if len(rows) < 2 or width < 2 or cells < 0.5 * len(rows) * width:
        return ""
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)


# ----- PDF -----


@dataclass
class _Line:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float
    bold: bool
    page: int
    region: float  # which block of the page, in reading order (columns are read one after the other)
    page_height: float = 0.0


@dataclass
class _Table:
    text: str
    top: float
    page: int
    region: float


def _is_bold(fontname):
    name = (fontname or "").lower()
    return any(word in name for word in ("bold", "black", "heavy", "semibold", ",bd", "-bd"))


def _word_lines(words):
    """Words (sorted in reading order inside one block) grouped into text lines."""
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        centre = (word["top"] + word["bottom"]) / 2
        for line in lines:
            if abs(centre - line["centre"]) <= 0.5 * max(word["size"], line["size"]):
                line["words"].append(word)
                break
        else:
            lines.append({"centre": centre, "size": word["size"], "words": [word]})
    return lines


def _reading_blocks(words, size):
    """Splits the words of a page into blocks in reading order: columns one after the other, a heading before its text.

    This is the "XY cut": look for an empty vertical strip (between columns) and cut there; if there is none, look for an
    empty horizontal strip (between a title and the text, or between paragraphs) and cut there; repeat on each part.
    """
    if len(words) < 2:
        return [words] if words else []

    def best_gap(spans):
        """The widest empty stretch between the (start, end) spans, as (width, cut position)."""
        best, reach = (0.0, 0.0), None
        for start, end in sorted(spans):
            if reach is not None and start - reach > best[0]:
                best = (start - reach, (start + reach) / 2)
            reach = end if reach is None else max(reach, end)
        return best

    x_width, x_cut = best_gap([(w["x0"], w["x1"]) for w in words])
    if x_width >= 1.2 * size:
        left = [w for w in words if (w["x0"] + w["x1"]) / 2 < x_cut]
        right = [w for w in words if (w["x0"] + w["x1"]) / 2 >= x_cut]
        if left and right:
            return _reading_blocks(left, size) + _reading_blocks(right, size)
    y_width, y_cut = best_gap([(w["top"], w["bottom"]) for w in words])
    if y_width >= 1.0 * size:
        above = [w for w in words if (w["top"] + w["bottom"]) / 2 < y_cut]
        below = [w for w in words if (w["top"] + w["bottom"]) / 2 >= y_cut]
        if above and below:
            return _reading_blocks(above, size) + _reading_blocks(below, size)
    return [words]


def _useful_word(word):
    text = word["text"]
    if "\ufffd" in text:
        return False
    if any(c.isalnum() for c in text):
        return True
    return len(text) == 1 and text not in "®™©"  # keep single punctuation and bullets, drop rows of decoration


def _read_page(page, page_number):
    """The text lines and tables of one page, each line labelled with the reading-order block it belongs to."""
    try:
        page = page.dedupe_chars(tolerance=1)  # some fonts are drawn twice (shadow, outline); keep each letter once
    except Exception:
        pass
    tables, boxes = [], []
    try:
        found = page.find_tables()
    except Exception:  # an odd drawing must not stop the whole file
        found = []
    for table in found:
        markdown = _pipe_table(table.extract())
        if markdown:
            tables.append([markdown, table.bbox[1]])
            boxes.append(table.bbox)

    def outside_tables(obj):
        if obj.get("object_type") != "char":
            return True
        cx, cy = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return not any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)

    text_page = page.filter(outside_tables) if boxes else page
    words = [w for w in text_page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False) if _useful_word(w)]
    if not words:
        return [], [_Table(markdown, top, page_number, 0.0) for markdown, top in tables]
    sizes = Counter()
    for w in words:
        sizes[round(w["size"] * 2) / 2] += len(w["text"])
    typical = sizes.most_common(1)[0][0] or 10

    lines = []
    blocks = _reading_blocks(words, typical)
    block_tops = []
    for block_number, block in enumerate(blocks):
        block_tops.append(min(w["top"] for w in block))
        for raw in _word_lines(block):
            line_words = sorted(raw["words"], key=lambda w: w["x0"])
            text = _tidy(" ".join(w["text"] for w in line_words))
            if not text:
                continue
            bold = sum(1 for w in line_words if _is_bold(w.get("fontname"))) >= 0.8 * len(line_words)
            size = round(statistics.median(w["size"] for w in line_words) * 2) / 2
            lines.append(
                _Line(
                    text,
                    min(w["x0"] for w in line_words),
                    max(w["x1"] for w in line_words),
                    min(w["top"] for w in line_words),
                    max(w["bottom"] for w in line_words),
                    size,
                    bold,
                    page_number,
                    block_number,
                    float(page.height),
                )
            )
    # a table goes after the last block that starts above it
    placed = []
    for markdown, top in tables:
        before = [i for i, t in enumerate(block_tops) if t <= top]
        placed.append(_Table(markdown, top, page_number, (max(before) if before else -1) + 0.5))
    return lines, placed


def _drop_page_furniture(lines, page_count):
    """Removes page numbers and the headers and footers that repeat on many pages."""
    def key(line):
        return re.sub(r"\d+", "#", line.text.lower()).strip()

    def in_margin(line):
        return line.top < 0.09 * line.page_height or line.bottom > 0.91 * line.page_height

    seen = {}
    for line in lines:
        if in_margin(line):
            seen.setdefault(key(line), set()).add(line.page)
    repeated = {k for k, pages in seen.items() if page_count >= 3 and len(pages) >= max(3, 0.4 * page_count)}
    return [line for line in lines if not (in_margin(line) and (key(line) in repeated or _PAGE_NUMBER.match(key(line))))]


def _heading_levels(lines, body_size):
    """Works out which (size, bold, capitals) styles are headings, and gives each a level (1 is the biggest)."""
    def style(line):
        # "1. Overview" in a big or bold font is a numbered heading; only symbol bullets are never headings
        if len(line.text) > 150 or _SYMBOL_BULLET.match(line.text):
            return None
        if line.size >= body_size * 1.12:
            return (line.size, line.bold)
        short = len(line.text) <= 90 and not re.search(r"[.,;]$", line.text)
        if short and line.bold and line.size >= body_size * 0.95:
            return (body_size, True)
        letters = [c for c in line.text if c.isalpha()]
        if short and len(letters) >= 4 and line.text.isupper() and line.size >= body_size * 0.95 and not line.text.endswith(":"):
            return (body_size, False)
        return None

    styles = [style(line) for line in lines]
    chosen = [s for s in styles if s]
    # if a large share of the document looks like headings the guess is wrong (slides, forms): only trust big text
    if len(chosen) > 0.35 * max(1, len(lines)):
        chosen = [s for s in chosen if s[0] >= body_size * 1.3]
        styles = [s if s in chosen else None for s in styles]
    ranking = sorted(set(chosen), key=lambda s: (-s[0], not s[1]))
    return {s: min(rank + 1, 4) for rank, s in enumerate(ranking)}, styles


def convert_pdf(path):
    try:
        pdf = pdfplumber.open(path)
    except Exception as error:
        name = type(error).__name__
        if "Password" in name or "Encrypt" in name:
            raise ConversionError("This PDF is password protected.") from None
        raise ConversionError(f"This PDF could not be read ({error}).") from None

    lines, tables, page_count = [], [], 0
    with pdf:
        page_count = len(pdf.pages)
        for number, page in enumerate(pdf.pages, start=1):
            try:
                found_lines, found_tables = _read_page(page, number)
            except Exception as error:
                raise ConversionError(f"Page {number} of this PDF could not be read ({error}).") from None
            lines += found_lines
            tables += found_tables

    lines = _drop_page_furniture(lines, page_count)
    if not lines and not tables:
        raise ConversionError("This PDF has no selectable text (it may be a scan). Scanned pages need OCR, which is not supported yet.")

    sizes = Counter()
    for line in lines:
        sizes[line.size] += len(line.text)
    body_size = sizes.most_common(1)[0][0] if sizes else 10
    levels, styles = _heading_levels(lines, body_size)
    style_of = {id(line): style for line, style in zip(lines, styles)}

    # reading order: page, then region (column), then top to bottom
    items = sorted([*lines, *tables], key=lambda item: (item.page, item.region, item.top))
    return _assemble(items, style_of, levels, body_size)


def _assemble(items, style_of, levels, body_size):
    blocks = []  # (page, kind, text)
    paragraph = None  # [kind, text, last line, left margin, first page]
    last_heading = None
    margins, widths = {}, {}
    for item in items:
        if isinstance(item, _Line):
            key = (item.page, item.region)
            widths[key] = max(widths.get(key, item.x1), item.x1)
            if not _BULLET.match(item.text):
                margins[key] = min(margins.get(key, item.x0), item.x0)

    def flush():
        nonlocal paragraph
        if paragraph:
            blocks.append((paragraph[4], paragraph[0], paragraph[1]))  # a paragraph belongs to the page it starts on
        paragraph = None

    for item in items:
        if isinstance(item, _Table):
            flush()
            blocks.append((item.page, "table", item.text))
            continue
        style = style_of.get(id(item))
        if style in levels:
            flush()
            level = levels[style]
            wrapped = (
                last_heading is not None
                and (last_heading.page, last_heading.region) == (item.page, item.region)
                and style_of.get(id(last_heading)) == style
                and 0 <= item.top - last_heading.bottom < item.size * 0.8
                and blocks
                and blocks[-1][1] == f"h{level}"
            )
            if wrapped:  # a title that wrapped onto a second line
                blocks[-1] = (item.page, f"h{level}", _join(blocks[-1][2], item.text))
            else:
                blocks.append((item.page, f"h{level}", item.text))
            last_heading = item
            continue
        bullet = _BULLET.match(item.text)
        if bullet:
            flush()
            marker = bullet.group(0).strip()
            prefix = "- " if _SYMBOL_BULLET.match(marker) or not marker else marker + " "  # keep "1." and "a)", turn symbols into "-"
            paragraph = ["li", prefix + (item.text[bullet.end():].strip() or item.text), item, margins.get((item.page, item.region), item.x0), item.page]
            continue
        if paragraph is None:
            paragraph = ["p", item.text, item, margins.get((item.page, item.region), item.x0), item.page]
            continue

        last = paragraph[2]
        same_place = last.page == item.page and last.region == item.region
        if same_place:
            line_height = max(1.0, last.bottom - last.top)
            gap = item.top - last.bottom
            indented = item.x0 - paragraph[3] > 1.0 * item.size and paragraph[0] == "p"
            region_width = max(1.0, widths[(item.page, item.region)] - paragraph[3])
            short_end = (last.x1 - paragraph[3]) < 0.6 * region_width and _TERMINAL.search(last.text)
            new_paragraph = gap > 0.6 * line_height or indented or bool(short_end)
        else:  # a new page or column: the sentence goes on if the last line was not finished
            new_paragraph = bool(_TERMINAL.search(last.text)) and not item.text[:1].islower()
        if new_paragraph:
            flush()
            paragraph = ["p", item.text, item, margins.get((item.page, item.region), item.x0), item.page]
        else:
            paragraph[1] = _join(paragraph[1], item.text)
            paragraph[2] = item
    flush()
    return _render(blocks)


def _render(blocks):
    """Blocks to the final text, remembering where each page starts."""
    parts, starts, position, previous_kind = [], [], 0, None
    seen_pages = set()
    for page, kind, text in blocks:
        if kind.startswith("h"):
            text = "#" * int(kind[1:]) + " " + text
        separator = ""
        if parts:
            separator = "\n" if kind == "li" and previous_kind == "li" else "\n\n"
        position += len(separator)
        if page not in seen_pages:
            seen_pages.add(page)
            starts.append((position, page))
        parts.append(separator + text)
        position += len(text)
        previous_kind = kind
    return Converted("".join(parts), starts)


# ----- Word -----


def convert_docx(path):
    """Word to Markdown with the MarkItDown package (headings, lists and tables come from the styles in the file)."""
    try:
        text = MarkItDown().convert(str(path)).text_content
    except Exception as error:
        raise ConversionError(f"This Word file could not be read ({error}). Only .docx files are supported, not old .doc files.") from None
    text = re.sub(r"(?m)^(\s*)[*+] ", r"\1- ", text or "")  # one bullet style: "- "
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ConversionError("This Word file has no text.")
    return Converted(text, [(0, 1)])


# ----- entry points -----


def convert(path):
    """Converted text of a .pdf or .docx file. Raises ConversionError (a ValueError) with a message for the user."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return convert_pdf(path)
    if suffix == ".docx":
        return convert_docx(path)
    raise ConversionError(f"Files of type {suffix or 'unknown'} cannot be converted.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert a PDF or Word file to standard text and show it.")
    parser.add_argument("file")
    parser.add_argument("-o", "--output", help="write the text to this file instead of printing it")
    args = parser.parse_args()
    result = convert(args.file)
    if args.output:
        Path(args.output).write_text(result.text, encoding="utf-8")
        print(f"Wrote {len(result.text)} characters, {len(result.page_starts)} pages, to {args.output}")
    else:
        print(result.text)
