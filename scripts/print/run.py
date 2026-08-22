import base64
import json
import os
import uuid
from time import time

import requests

BASE_URL = "https://printme.uwe.ac.uk"
PRINT_CENTER = f"{BASE_URL}/MyPrintCenter/"
LOGON_URL = f"{BASE_URL}/PharosAPI/logon"

USERNAME = os.environ.get("PHAROS_USERNAME")
PASSWORD = os.environ.get("PHAROS_PASSWORD")


def _require_creds() -> tuple[str, str]:
    if not USERNAME or not PASSWORD:
        raise ValueError("PHAROS_USERNAME and PHAROS_PASSWORD env vars must be set")
    return USERNAME, PASSWORD


def login(session: requests.Session, username: str, password: str) -> dict:
    """Pharos auth is a single GET with credentials packed into a custom
    Authorization scheme (base64 "user:pass", same shape as HTTP Basic),
    not a form POST - captured from the browser's Network tab."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()

    resp = session.get(
        LOGON_URL,
        params={
            "KeepMeLoggedIn": "yes",
            "includeprintjobs": "no",
            "includedeviceactivity": "yes",
            "includeprivileges": "yes",
            "includecostcenters": "yes",
            "excudeLocation": "yes",
            "notRefreshBalance": "no",
            "_request": str(uuid.uuid4()),
            "_": str(int(time() * 1000)),
        },
        headers={
            "X-Authorization": f"PHAROS-USER {token}",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
            "Referer": PRINT_CENTER,
        },
    )
    resp.raise_for_status()
    body = resp.json()

    if (
        isinstance(body, dict)
        and isinstance(body.get("Status"), int)
        and body["Status"] >= 300
    ):
        raise RuntimeError(
            body.get("DeveloperMessage") or body.get("UserMessage") or "login failed"
        )

    if not session.cookies.get("PharosAPI.X-PHAROS-USER-TOKEN"):
        raise RuntimeError(
            "Login did not return a session token - the API response shape "
            f"may have changed. Response body: {body!r}"
        )

    return body


def submit_print_job(
    session: requests.Session,
    user_id: str,
    pdf_bytes: bytes,
    pdf_name: str,
    mono: bool,
    copies: int,
) -> dict:
    metadata = {
        "FinishingOptions": {
            "Mono": mono,
            "Duplex": False,
            "PagesPerSide": "1",
            "Copies": str(copies),
            "DefaultPageSize": "A4",
            "PageRange": "",
        },
        "PrinterName": "",
    }

    resp = session.post(
        f"{BASE_URL}/PharosAPI/users/{user_id}/printjobs",
        data={"MetaData": json.dumps(metadata)},
        files={"content": (pdf_name, pdf_bytes, "application/pdf")},
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": PRINT_CENTER},
    )
    resp.raise_for_status()
    return resp.json()


def run(
    file: bytes | None = None,
    *,
    colour: str = "false",
    copies: str = "1",
    filename: str = "document.pdf",
):
    username, password = _require_creds()

    if not file:
        raise ValueError("a PDF `file` is required")

    colour_bool = colour.strip().lower() == "true"
    mono = not colour_bool

    try:
        copies_n = int(copies)
        if copies_n < 1:
            raise ValueError
    except ValueError:
        raise ValueError("copies must be a positive integer")

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    session = requests.Session()
    logon_body = login(session, username, password)
    user_id = logon_body["Identifier"]
    job = submit_print_job(session, user_id, file, filename, mono, copies_n)

    body = {
        "name": job.get("Name", filename),
        "colour": colour_bool,
        "copies": copies_n,
        "state": job.get("PrintState", "Unknown"),
    }

    return json.dumps(body, indent=2).encode(), "json"
