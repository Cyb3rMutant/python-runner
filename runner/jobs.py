from fastapi import APIRouter, HTTPException, Request, Response
from starlette.datastructures import UploadFile

from .media_types import MEDIA_TYPES
from .registry import JOBS

router = APIRouter()


def run_job(name: str, *args, **kwargs):
    if name not in JOBS:
        raise HTTPException(status_code=404, detail=f"no job named '{name}'")

    try:
        content, file_type = JOBS[name](*args, **kwargs)
    except Exception as exc:
        print(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    media_type = MEDIA_TYPES.get(file_type, "application/octet-stream")
    headers = {"Content-Disposition": f'attachment; filename="data.{file_type}"'}

    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/{name}")
def run_job_get(name: str):
    return run_job(name)


@router.post("/{name}")
async def run_job_post(name: str, request: Request):
    form = await request.form()

    file_bytes = None
    params = {}
    for key, value in form.multi_items():
        if isinstance(value, UploadFile):
            file_bytes = await value.read()
        else:
            params[key] = value

    return run_job(name, file_bytes, **params)
