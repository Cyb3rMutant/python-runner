from fastapi import FastAPI, HTTPException, Response

from .registry import JOBS

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "csv": "text/csv",
    "txt": "text/plain",
    "json": "application/json",
    "png": "image/png",
    "jpg": "image/jpeg",
}


app = FastAPI(title="Python Runner")


@app.get("/jobs")
def list_jobs():
    return {"jobs": sorted(JOBS)}


@app.get("/jobs/{name}")
def run_job(name: str):
    if name not in JOBS:
        raise HTTPException(status_code=404, detail=f"no job named '{name}'")

    try:
        content, file_type = JOBS[name]()
    except Exception as exc:
        print(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    media_type = MEDIA_TYPES.get(file_type, "application/octet-stream")
    headers = {"Content-Disposition": f'attachment; filename="data.{file_type}"'}

    return Response(content=content, media_type=media_type, headers=headers)
