import base64
import os

import requests
from fastapi import APIRouter, Request

from .ai_router import IMAGE_REQUIRED, JOB_TOOLS, decide_what_to_call
from .media_types import MEDIA_TYPES
from .registry import JOBS

router = APIRouter()

WAHA_URL = "https://waha.yzd.uk"
WAHA_SESSION = "default"
WAHA_API_KEY = os.environ.get("WAHA_API_KEY")

TARGET_GROUP = "120363404740054418@g.us"


def _waha_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    return headers


def _waha_send_text(chat_id: str, text: str) -> None:
    requests.post(
        f"{WAHA_URL}/api/sendText",
        json={"session": WAHA_SESSION, "chatId": chat_id, "text": text},
        headers=_waha_headers(),
    ).raise_for_status()


def _waha_send_file(chat_id: str, content: bytes, file_type: str) -> None:
    mimetype = MEDIA_TYPES.get(file_type, "application/octet-stream")

    requests.post(
        f"{WAHA_URL}/api/sendFile",
        json={
            "session": WAHA_SESSION,
            "chatId": chat_id,
            "file": {
                "mimetype": mimetype,
                "filename": f"result.{file_type}",
                "data": base64.b64encode(content).decode(),
            },
        },
        headers=_waha_headers(),
    ).raise_for_status()


@router.post("/webhook/waha")
async def waha_webhook(request: Request):
    data = await request.json()

    # Only process incoming messages
    if data.get("event") != "message.any":
        return {"status": "ignored"}

    payload = data.get("payload", {})

    body = payload.get("body") or ""
    chat_id = payload.get("_data", {}).get("id", {}).get("remote") or TARGET_GROUP

    print("Message:", body)
    print("Chat:", chat_id)

    if not body.startswith("bot>"):
        return {"status": "ignored"}

    text = body[len("bot>") :].strip()

    media = payload.get("media") if payload.get("hasMedia") else None
    image_attached = bool(media and media.get("url"))

    decision = decide_what_to_call(text)
    print(decision)
    if not decision or decision["function"] not in JOB_TOOLS:
        _waha_send_text(
            chat_id, "Sorry, I couldn't work out what to do with that."
        )
        return {"status": "ok"}

    function_name = decision["function"]
    if function_name in IMAGE_REQUIRED and not image_attached:
        _waha_send_text(chat_id, "Attach an image with your bot> request.")
        return {"status": "ok"}

    file_bytes = None
    if media and media.get("url"):
        image_resp = requests.get(media["url"])
        image_resp.raise_for_status()
        file_bytes = image_resp.content

    job_name, fixed_args = JOB_TOOLS[function_name]
    try:
        result = JOBS[job_name](file_bytes, **fixed_args, **decision["arguments"])
    except Exception as exc:
        print(exc)
        _waha_send_text(chat_id, f"Couldn't do that: {exc}")
        return {"status": "ok"}

    content, file_type, meta = result if len(result) == 3 else (*result, {})

    _waha_send_file(chat_id, content, file_type)
    if meta.get("old_url"):
        _waha_send_text(chat_id, f"This used to point to: {meta['old_url']}")

    return {"status": "ok"}
