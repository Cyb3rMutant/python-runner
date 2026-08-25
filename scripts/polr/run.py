"""Polr admin link manager — uses the internal /api/v3 endpoint the
admin dashboard itself calls for edits, since the public API doesn't
expose that operation. Every action returns a black & white QR code
for the resulting short link.
"""

import os
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from scripts.qr_style.run import run as generate_styled_qr

BASE_URL = "https://uwe.isoc.link"
LOGIN_URL = f"{BASE_URL}/login"
EDIT_LONG_URL_URL = f"{BASE_URL}/api/v3/admin/edit_link_long_url"
SHORTEN_V2_URL = f"{BASE_URL}/api/v2/action/shorten"
LOOKUP_V2_URL = f"{BASE_URL}/api/v2/action/lookup"

USERNAME = os.environ.get("POLR_USERNAME")
PASSWORD = os.environ.get("POLR_PASSWORD")
API_KEY = os.environ.get("POLR_API_KEY")


def _require_admin_creds() -> tuple[str, str]:
    if not USERNAME or not PASSWORD:
        raise ValueError("POLR_USERNAME and POLR_PASSWORD env vars must be set")
    return USERNAME, PASSWORD


def _require_api_key() -> None:
    if not API_KEY:
        raise ValueError("POLR_API_KEY env var must be set")


def login(session: requests.Session, username: str, password: str) -> None:
    """Load the login page, harvest any hidden fields (CSRF token etc.),
    then POST credentials alongside them."""
    page = session.get(LOGIN_URL)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")

    form = soup.find("form")
    payload = {}
    if form:
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                payload[name] = inp.get("value", "")

    payload["username"] = username
    payload["password"] = password

    resp = session.post(LOGIN_URL, data=payload, headers={"Referer": LOGIN_URL})
    resp.raise_for_status()

    if "login" in resp.url and resp.request.method == "GET":
        raise RuntimeError("Login looks like it failed (redirected back to /login)")


def xsrf_headers(session: requests.Session) -> dict:
    """Laravel issues an XSRF-TOKEN cookie on every response; echoing it
    back as X-XSRF-TOKEN is what lets state-changing (POST/PUT/DELETE)
    routes pass CSRF verification. GET routes don't need this."""
    token = session.cookies.get("XSRF-TOKEN")
    return {"X-XSRF-TOKEN": unquote(token)} if token else {}


def edit_long_url(session: requests.Session, link_ending: str, new_long_url: str) -> str:
    """Plain-text response (e.g. 'success'), not JSON."""
    resp = session.post(
        EDIT_LONG_URL_URL,
        data={"link_ending": link_ending, "new_long_url": new_long_url},
        headers={"X-Requested-With": "XMLHttpRequest", **xsrf_headers(session)},
    )
    resp.raise_for_status()
    return resp.text.strip()


def shorten_v2(url: str, custom_ending: str) -> str:
    """v2 API — plain GET, returns the short URL as raw text (not JSON)."""
    resp = requests.get(
        SHORTEN_V2_URL, params={"key": API_KEY, "url": url, "custom_ending": custom_ending}
    )
    resp.raise_for_status()
    return resp.text.strip()


def lookup_v2(url_ending: str) -> str | None:
    """v2 API — GET, plain-text body on success. A nonexistent ending
    500s with Polr's HTML error page rather than a clean 404, so treat
    that as "not found" instead of raising."""
    resp = requests.get(
        LOOKUP_V2_URL, params={"key": API_KEY, "url_ending": url_ending}
    )
    if resp.status_code == 500:
        return None
    resp.raise_for_status()
    return resp.text.strip()


def add(ending: str, url: str) -> None:
    _require_api_key()
    if lookup_v2(ending) is not None:
        raise ValueError(f"'{ending}' already exists - use action=force_update to overwrite it")
    shorten_v2(url, ending)


def force_update(ending: str, url: str) -> None:
    username, password = _require_admin_creds()
    session = requests.Session()
    login(session, username, password)
    result = edit_long_url(session, ending, url)
    if result.lower() != "success":
        raise RuntimeError(f"update failed: {result}")


def get(ending: str) -> str:
    _require_api_key()
    long_url = lookup_v2(ending)
    if long_url is None:
        raise ValueError(f"'{ending}' does not exist")
    return long_url


def run(
    file: bytes | None = None,
    *,
    action: str = "get",
    ending: str | None = None,
    url: str | None = None,
):
    if not ending:
        raise ValueError("`ending` is required")

    if action == "add":
        if not url:
            raise ValueError("`url` is required for action=add")
        add(ending, url)

    elif action == "force_update":
        if not url:
            raise ValueError("`url` is required for action=force_update")
        force_update(ending, url)

    elif action == "get":
        get(ending)

    else:
        raise ValueError(f"unknown action: {action!r} (expected add|force_update|get)")

    png_bytes, file_type = generate_styled_qr(data=f"{BASE_URL}/{ending}")
    return png_bytes, file_type
