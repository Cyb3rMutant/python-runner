import io

from PIL import Image
from reportlab.lib.pagesizes import A3
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def image_to_a3_pdf(image_bytes: bytes) -> bytes:
    a3_width, a3_height = A3

    img = Image.open(io.BytesIO(image_bytes))
    img_width, img_height = img.size

    # Scale to fit inside A3 while keeping aspect ratio, then center.
    scale = min(a3_width / img_width, a3_height / img_height)
    new_width = img_width * scale
    new_height = img_height * scale
    x = (a3_width - new_width) / 2
    y = (a3_height - new_height) / 2

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A3)
    c.drawImage(ImageReader(img), x, y, width=new_width, height=new_height)
    c.showPage()
    c.save()

    return buffer.getvalue()


def run(image_bytes: bytes):
    return image_to_a3_pdf(image_bytes), "pdf"
