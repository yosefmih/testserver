from io import BytesIO

from pypdf import PdfReader, PdfWriter


def count_pages(data: bytes) -> int:
    return len(PdfReader(BytesIO(data)).pages)


def extract_pages(data: bytes, first_page: int, last_page: int) -> bytes:
    reader = PdfReader(BytesIO(data))
    writer = PdfWriter()
    for index in range(first_page - 1, last_page):
        writer.add_page(reader.pages[index])
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
