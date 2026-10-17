import io

import fitz
from PIL import Image


def pdf_to_jpg(pdf_bytes: bytes, page: int, dpi: int) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page < 1 or page > doc.page_count:
            raise ValueError(f"page {page} out of range - PDF has {doc.page_count} page(s)")

        pix = doc[page - 1].get_pixmap(dpi=dpi)
    finally:
        doc.close()

    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def run(file: bytes | None = None, *, page: str = "1", dpi: str = "150"):
    if not file:
        raise ValueError("a PDF file is required")

    try:
        page_n = int(page)
    except ValueError:
        raise ValueError("page must be an integer")

    try:
        dpi_n = int(dpi)
    except ValueError:
        raise ValueError("dpi must be an integer")

    return pdf_to_jpg(file, page_n, dpi_n), "jpg"
