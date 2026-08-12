"""
Maps a job name (used in the URL, e.g. GET /timetable) to the
callable that runs it.

To add a new script:
  1. Create scripts/<name>/ with a `run()` function that does the work and
     returns `(content: bytes, file_type: str)`, e.g. `(pdf_bytes, "pdf")`.
     No import from `runner` needed - the server looks up the media type
     from `file_type` itself.
     If the job needs input, give `run()` a leading `file: bytes | None`
     parameter for an uploaded file, plus any other keyword-only parameters
     for extra form fields (values arrive as strings; the job converts what
     it needs, e.g. `int(threshold)`) - the server calls it via POST
     instead of GET, forwarding the uploaded file and form fields.
  2. Import it below and add it to JOBS.
"""

from scripts.img_a3.run import run as img_a3
from scripts.qr_style.run import run as qr_style
from scripts.timetable.run import run as timetable

JOBS = {
    "timetable": timetable,
    "img-a3": img_a3,
    "qr-style": qr_style,
}
