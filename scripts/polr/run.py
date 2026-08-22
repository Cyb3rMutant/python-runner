"""Polr admin link manager — uses the internal /api/v3 endpoint the
admin dashboard itself calls, since the public API doesn't expose this data.
"""

import json
import os
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://uwe.isoc.link"
LOGIN_URL = f"{BASE_URL}/login"
LINKS_URL = f"{BASE_URL}/api/v3/admin/get_admin_links"
EDIT_LONG_URL_URL = f"{BASE_URL}/api/v3/admin/edit_link_long_url"
AVAIL_CHECK_URL = f"{BASE_URL}/api/v3/link_avail_check"
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


def fetch_links(session: requests.Session) -> dict:
    resp = session.get(
        LINKS_URL,
        params={"draw": 1, "start": 0, "length": 10000},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    resp.raise_for_status()
    return resp.json()


def extract_short_code(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    span = soup.find("span", class_="cellmain")
    return span.get_text(strip=True) if span else None


def extract_long_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    a = soup.find("a", class_="cellmain")
    return str(a.get("href")) if a else None


def extract_clicks(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    span = soup.find("span", class_="cellmain")
    return span.get_text(strip=True) if span else None


def parse_rows(payload: dict) -> list[dict]:
    rows = []
    for row in payload.get("data", []):
        short_code = extract_short_code(row["short_url"])
        rows.append(
            {
                "id": row["id"],
                "short_url": f"{BASE_URL}/{short_code}" if short_code else None,
                "long_url": extract_long_url(row["long_url"]),
                "clicks": extract_clicks(row["clicks"]),
                "created_at": row["created_at"],
                "creator": row["creator"],
                "is_disabled": bool(row["is_disabled"]),
            }
        )
    return rows


def edit_long_url(
    session: requests.Session, link_ending: str, new_long_url: str
) -> str:
    """Plain-text response (e.g. 'success'), not JSON."""
    resp = session.post(
        EDIT_LONG_URL_URL,
        data={"link_ending": link_ending, "new_long_url": new_long_url},
        headers={"X-Requested-With": "XMLHttpRequest", **xsrf_headers(session)},
    )
    resp.raise_for_status()
    return resp.text.strip()


def check_avail(session: requests.Session, link_ending: str) -> str:
    """Plain-text response (e.g. 'available'), not JSON."""
    resp = session.post(
        AVAIL_CHECK_URL,
        data={"link_ending": link_ending},
        headers={"X-Requested-With": "XMLHttpRequest", **xsrf_headers(session)},
    )
    resp.raise_for_status()
    return resp.text.strip()


def shorten_v2(url: str, custom_ending: str | None = None) -> str:
    """v2 API — plain GET, returns the short URL as raw text (not JSON)."""
    params = {"key": API_KEY, "url": url}
    if custom_ending:
        params["custom_ending"] = custom_ending
    resp = requests.get(SHORTEN_V2_URL, params=params)
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


def load_from_file(data: bytes) -> list[dict]:
    return parse_rows(json.loads(data))


def load_from_api() -> list[dict]:
    username, password = _require_admin_creds()
    session = requests.Session()
    login(session, username, password)
    return parse_rows(fetch_links(session))


def run(
    file: bytes | None = None,
    *,
    action: str = "list",
    ending: str | None = None,
    url: str | None = None,
    new_long_url: str | None = None,
    custom_ending: str | None = None,
):
    if action == "list":
        rows = load_from_file(file) if file else load_from_api()
        body = {"links": rows, "count": len(rows)}

    elif action == "edit":
        if not ending or not new_long_url:
            raise ValueError("`ending` and `new_long_url` are required for action=edit")
        username, password = _require_admin_creds()
        session = requests.Session()
        login(session, username, password)
        body = {"result": edit_long_url(session, ending, new_long_url)}

    elif action == "check":
        if not ending:
            raise ValueError("`ending` is required for action=check")
        username, password = _require_admin_creds()
        session = requests.Session()
        login(session, username, password)
        body = {"result": check_avail(session, ending)}

    elif action == "shorten":
        if not url:
            raise ValueError("`url` is required for action=shorten")
        _require_api_key()
        body = {"short_url": shorten_v2(url, custom_ending)}

    elif action == "lookup":
        if not ending:
            raise ValueError("`ending` is required for action=lookup")
        _require_api_key()
        result = lookup_v2(ending)
        body = {"long_url": result}

    else:
        raise ValueError(
            f"unknown action: {action!r} (expected list|edit|check|shorten|lookup)"
        )

    return json.dumps(body, indent=2).encode(), "json"
