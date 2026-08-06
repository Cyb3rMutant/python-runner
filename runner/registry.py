"""
Maps a job name (used in the URL, e.g. GET /jobs/timetable) to the
callable that runs it.

To add a new script:
  1. Create scripts/<name>/ with a `run()` function that does the work and
     returns `(content: bytes, file_type: str)`, e.g. `(pdf_bytes, "pdf")`.
     No import from `runner` needed - the server looks up the media type
     from `file_type` itself.
  2. Import it below and add it to JOBS.
"""

from scripts.timetable.run import run as timetable

JOBS = {
    "timetable": timetable,
}
