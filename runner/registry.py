"""
Maps a job name (used in the URL, e.g. POST /jobs/timetable/run) to the
callable that runs it.

To add a new script:
  1. Create scripts/<name>/ with a `run()` function that does the work and
     returns a `runner.models.JobFile` (the file content, in memory).
  2. Import it below and add it to JOBS.
"""

from scripts.timetable.run import run as timetable

JOBS = {
    "timetable": timetable,
}
