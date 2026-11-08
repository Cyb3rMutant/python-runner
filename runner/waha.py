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

TARGET_GROUP = "120363429725042048@g.us"


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


def _waha_send_file(chat_id: str, content: bytes, file_type: str, caption: str | None = None) -> None:
    mimetype = MEDIA_TYPES.get(file_type, "application/octet-stream")

    body = {
        "session": WAHA_SESSION,
        "chatId": chat_id,
        "file": {
            "mimetype": mimetype,
            "filename": f"result.{file_type}",
            "data": base64.b64encode(content).decode(),
        },
    }
    if caption:
        body["caption"] = caption

    requests.post(
        f"{WAHA_URL}/api/sendFile",
        json=body,
        headers=_waha_headers(),
    ).raise_for_status()


def _link_caption(function_name: str, meta: dict) -> str | None:
    short_url = meta.get("short_url")
    if not short_url:
        return None
    long_url = meta.get("long_url")

    if function_name == "get_link":
        return f"{short_url}\nPoints to: {long_url}"
    if meta.get("old_url"):
        return f"Updated {short_url}\nOld: {meta['old_url']}\nNew: {long_url}"
    return f"Created {short_url}\nPoints to: {long_url}"


def _format_confidence(confidence: float | None) -> str:
    if confidence is None:
        return "Confidence: unknown"
    return f"Confidence: {confidence:.0%}"


@router.post("/webhook/waha")
async def waha_webhook(request: Request):
    data = await request.json()

    # Only process incoming messages
    if data.get("event") != "message.any":
        return {"status": "ignored"}

    payload = data.get("payload", {})

    body = payload.get("body") or ""
    chat_id = payload.get("_data", {}).get("id", {}).get("remote")

    if chat_id != TARGET_GROUP:
        return {"status": "ignored"}

    print("Message:", body)

    if not body.startswith("bot>"):
        return {"status": "ignored"}

    text = body[len("bot>") :].strip()

    # Easter egg - answered directly, never reaches the model.
    if text.lower() == "kys":
        _waha_send_text(chat_id, "yes master")
        return {"status": "ok"}

    media = payload.get("media") if payload.get("hasMedia") else None
    image_attached = bool(media and media.get("url"))

    decision = decide_what_to_call(text)
    print(decision)
    conf = _format_confidence(decision["confidence"])

    function_name = decision["function"]
    if function_name not in JOB_TOOLS:
        reason = decision["reason"] or f"unknown function {function_name!r}"
        _waha_send_text(chat_id, f"Sorry, I couldn't do that - {reason}.\n{conf}")
        return {"status": "ok"}

    if function_name in IMAGE_REQUIRED and not image_attached:
        _waha_send_text(
            chat_id,
            f"Failed: {function_name} needs an image - attach one with your bot> request.\n{conf}",
        )
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
        _waha_send_text(chat_id, f"Failed: {function_name} errored - {exc}\n{conf}")
        return {"status": "ok"}

    content, file_type, meta = result if len(result) == 3 else (*result, {})

    _waha_send_file(chat_id, content, file_type, caption=_link_caption(function_name, meta))
    if meta.get("short_url"):
        # Separate message so it's easy to long-press copy / forward.
        _waha_send_text(chat_id, meta["short_url"])
    _waha_send_text(chat_id, f"Done: {function_name}\n{conf}")

    return {"status": "ok"}
