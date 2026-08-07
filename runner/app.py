from fastapi import FastAPI, File, HTTPException, Response, UploadFile

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


def _run_job(name: str, *args):
    if name not in JOBS:
        raise HTTPException(status_code=404, detail=f"no job named '{name}'")

    try:
        content, file_type = JOBS[name](*args)
    except Exception as exc:
        print(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    media_type = MEDIA_TYPES.get(file_type, "application/octet-stream")
    headers = {"Content-Disposition": f'attachment; filename="data.{file_type}"'}

    return Response(content=content, media_type=media_type, headers=headers)


@app.get("/{name}")
def run_job(name: str):
    return _run_job(name)


@app.post("/{name}")
async def run_job_with_input(name: str, file: UploadFile = File(...)):
    return _run_job(name, await file.read())
