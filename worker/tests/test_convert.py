"""Tests for turning PDF and Word files into standard text (common/convert.py).

The PDFs are built by hand in the tests (a few lines of positioned text), so no sample files are needed.
"""
import pytest

from common.convert import ConversionError, convert


def build_pdf(pages):
    """pages: a list of pages; each page is a list of (x, y_from_top, size, bold, text). Returns the PDF bytes."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"]
    kids = []
    for lines in pages:
        content = "".join(
            f"BT /{'F2' if bold else 'F1'} {size} Tf {x} {792 - y} Td ({text.replace('(', '[').replace(')', ']')}) Tj ET\n"
            for x, y, size, bold, text in lines
        )
        page_number = len(objects) + 1
        kids.append(f"{page_number} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {page_number + 1} 0 R "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content}endstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def paragraph(x, y, size, lines, pitch=14):
    return [(x, y + i * pitch, size, False, text) for i, text in enumerate(lines)]


def report_page(number, body):
    """A page with a repeated header and a page number footer around the body lines."""
    return [(72, 40, 9, False, "ACME Annual Report"), (300, 750, 9, False, f"Page {number}")] + body


def test_pdf_headings_paragraphs_headers_footers_and_hyphens(tmp_path):
    page1 = report_page(1, [(72, 100, 22, True, "Annual Report 2025"), (72, 140, 15, True, "1. Overview")]
                        + paragraph(72, 170, 11, ["The company grew steadily during the year and this", "growth came from three main markets. In the exam-", "ple of Canada, sales doubled."])
                        + paragraph(72, 240, 11, ["A second paragraph starts here after a gap and it", "continues for a little while until the page ends and"]))
    page2 = report_page(2, paragraph(72, 100, 11, ["then it carries on at the top of the next page."])
                        + [(72, 140, 15, True, "2. Outlook")]
                        + paragraph(72, 170, 11, ["Next year looks good."]))
    page3 = report_page(3, paragraph(72, 100, 11, ["The end of the report."]))
    path = tmp_path / "report.pdf"
    path.write_bytes(build_pdf([page1, page2, page3]))

    result = convert(path)
    text = result.text
    assert text.startswith("# Annual Report 2025")
    assert "## 1. Overview" in text and "## 2. Outlook" in text
    assert "ACME Annual Report" not in text and "Page 1" not in text and "Page 2" not in text
    assert "the exam" in text and "example of Canada" in text  # the hyphenated word is whole again
    assert "until the page ends and then it carries on at the top of the next page." in text  # one paragraph across a page break
    paragraphs = text.split("\n\n")
    assert any(p.startswith("The company grew steadily") and p.endswith("sales doubled.") for p in paragraphs)
    assert any(p.startswith("A second paragraph") for p in paragraphs)
    assert [page for _, page in result.page_starts] == [1, 2, 3]
    assert text[result.page_starts[1][0]:].startswith("## 2. Outlook")  # a paragraph that runs over belongs to the page it began on


def test_pdf_two_columns_are_read_one_after_the_other(tmp_path):
    left = paragraph(72, 100, 11, [f"Left column line {n} with some words in it" for n in range(1, 13)])
    right = paragraph(330, 100, 11, [f"Right column line {n} with other words in it" for n in range(1, 13)])
    path = tmp_path / "columns.pdf"
    path.write_bytes(build_pdf([left + right]))
    text = convert(path).text
    assert text.index("Left column line 12") < text.index("Right column line 1 ")


def test_pdf_lists_become_list_items(tmp_path):
    lines = [(72, 100, 11, False, "Things to bring:"), (90, 120, 11, False, "- a passport"), (90, 135, 11, False, "- a ticket and a long"), (97, 150, 11, False, "second line of that item"), (90, 165, 11, False, "- some money")]
    path = tmp_path / "list.pdf"
    path.write_bytes(build_pdf([lines]))
    text = convert(path).text
    assert "- a passport\n- a ticket and a long second line of that item\n- some money" in text


def test_pdf_numbered_lists_keep_their_numbers(tmp_path):
    lines = [(72, 100, 11, False, "Steps:"), (90, 120, 11, False, "1. Open the box"), (90, 135, 11, False, "2. Read the rules")]
    path = tmp_path / "steps.pdf"
    path.write_bytes(build_pdf([lines]))
    assert "1. Open the box\n2. Read the rules" in convert(path).text


def test_a_pdf_with_no_text_or_a_broken_one_gives_a_clear_error(tmp_path):
    empty = tmp_path / "scan.pdf"
    empty.write_bytes(build_pdf([[]]))
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 not really")
    with pytest.raises(ConversionError, match="no selectable text"):
        convert(empty)
    with pytest.raises(ConversionError, match="could not be read"):
        convert(broken)


def test_word_headings_lists_and_tables(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Service Agreement", level=1)
    document.add_paragraph("This agreement is made between the two parties named below.")
    document.add_heading("Payment", level=2)
    document.add_paragraph("Fees are due monthly.")
    document.add_paragraph("Late fees apply", style="List Bullet")
    document.add_paragraph("Interest is charged", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Plan", "Price"
    table.rows[1].cells[0].text, table.rows[1].cells[1].text = "Basic", "$10"
    path = tmp_path / "agreement.docx"
    document.save(path)

    text = convert(path).text
    assert text.startswith("# Service Agreement\n\nThis agreement is made")
    assert "## Payment\n\nFees are due monthly." in text
    assert "- Late fees apply\n- Interest is charged" in text
    assert "| Plan | Price |\n| --- | --- |\n| Basic | $10 |" in text


def test_unsupported_and_damaged_word_files(tmp_path):
    damaged = tmp_path / "bad.docx"
    damaged.write_bytes(b"this is not a zip file")
    with pytest.raises(ConversionError, match="could not be read"):
        convert(damaged)
    with pytest.raises(ConversionError, match="cannot be converted"):
        convert(tmp_path / "old.doc")
