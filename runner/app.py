import os
import subprocess
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from . import github_ops
from .models import RunRequest
from .registry import JOBS

_locks = {name: threading.Lock() for name in JOBS}


def _configure_git():
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", "/app"], check=True
    )
    subprocess.run(
        [
            "git",
            "config",
            "--global",
            "user.name",
            os.environ.get("GIT_USER_NAME", "d"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "config",
            "--global",
            "user.email",
            os.environ.get("GIT_USER_EMAIL", "dev@yzd.uk"),
        ],
        check=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_git()
    yield


app = FastAPI(title="Python Runner", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/jobs")
def list_jobs():
    return {"jobs": sorted(JOBS)}


@app.post("/jobs/{name}/run")
async def run_job(name: str, body: RunRequest = RunRequest()):
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

        if body.github.push:
            github_result = await run_in_threadpool(
                github_ops.commit_and_push, body.github.message
            )
            headers["X-Github-Pushed"] = str(github_result.pushed).lower()
            if github_result.commit:
                headers["X-Github-Commit"] = github_result.commit
            if github_result.detail:
                headers["X-Github-Detail"] = github_result.detail

        return Response(
            content=job_file.content,
            media_type=job_file.media_type,
            headers=headers,
        )
    finally:
        lock.release()
