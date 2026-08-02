import threading

from fastapi import FastAPI, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from .registry import JOBS

_locks = {name: threading.Lock() for name in JOBS}


app = FastAPI(title="Python Runner")


@app.get("/jobs")
def list_jobs():
    return {"jobs": sorted(JOBS)}


@app.post("/jobs/{name}/run")
async def run_job(name: str):
    if name not in JOBS:
        raise HTTPException(status_code=404, detail=f"no job named '{name}'")

    lock = _locks[name]
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail=f"job '{name}' is already running")

    try:
        try:
            job_file = await run_in_threadpool(JOBS[name])
        except Exception as exc:
            print(exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        headers = {"Content-Disposition": f'attachment; filename="{job_file.filename}"'}

        return Response(
            content=job_file.content,
            media_type=job_file.media_type,
            headers=headers,
        )
    finally:
        lock.release()
