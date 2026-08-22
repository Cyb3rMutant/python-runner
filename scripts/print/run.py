import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "https://printme.uwe.ac.uk"
PRINT_CENTER = f"{BASE_URL}/MyPrintCenter/"
PROFILE = Path(__file__).parent / ".pharos-profile"

USERNAME = os.environ.get("PHAROS_USERNAME")
PASSWORD = os.environ.get("PHAROS_PASSWORD")


def _submit(pdf_bytes: bytes, pdf_name: str, mono: bool, copies: int) -> dict:
    with sync_playwright() as p:
        context = p.firefox.launch_persistent_context(str(PROFILE), headless=True)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(PRINT_CENTER)
        page.wait_for_timeout(1500)

        cookies = context.cookies()

        logged_in = any(
            c["name"] == "PharosAPI.X-PHAROS-USER-TOKEN" and c["value"] for c in cookies
        )

        if not logged_in:
            username = page.locator('input[id="input-login-username"]').first
            password = page.locator('input[id="input-login-password"]').first

            username.fill(USERNAME)
            password.fill(PASSWORD)

            remember = page.locator("#input-login-rememberme")
            if remember.count() > 0 and not remember.is_checked():
                remember.check()

            password.press("Enter")

            page.wait_for_timeout(20000)

            cookies = context.cookies()

            logged_in = any(
                c["name"] == "PharosAPI.X-PHAROS-USER-TOKEN" and c["value"]
                for c in cookies
            )

            if not logged_in:
                context.close()
                raise RuntimeError(
                    "Automatic login failed - the login page may have changed "
                    "or requires another step."
                )

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

        result = page.evaluate(
            """
            async ({ pdfName, pdfBytes, metadata }) => {
                const form = new FormData();

                form.append(
                    "MetaData",
                    JSON.stringify(metadata)
                );

                const bytes = new Uint8Array(pdfBytes);

                const blob = new Blob(
                    [bytes],
                    { type: "application/pdf" }
                );

                form.append(
                    "content",
                    blob,
                    pdfName
                );

                const response = await fetch(
                    "/PharosAPI/users/bBCGqYxxYVyMI0cEOY8nKA2/printjobs",
                    {
                        method: "POST",
                        body: form,
                        credentials: "include",
                        headers: {
                            "X-Requested-With": "XMLHttpRequest"
                        }
                    }
                );

                return {
                    status: response.status,
                    ok: response.ok,
                    text: await response.text()
                };
            }
            """,
            {
                "pdfName": pdf_name,
                "pdfBytes": list(pdf_bytes),
                "metadata": metadata,
            },
        )

        context.close()

        if not result["ok"]:
            raise RuntimeError(f"Upload failed: HTTP {result['status']} - {result['text']}")

        return json.loads(result["text"])


def run(
    file: bytes | None = None,
    *,
    colour: str = "mono",
    copies: str = "1",
    filename: str = "document.pdf",
):
    if not USERNAME or not PASSWORD:
        raise ValueError(
            "PHAROS_USERNAME and PHAROS_PASSWORD env vars must be set"
        )

    if not file:
        raise ValueError("a PDF `file` is required")

    colour = colour.lower()
    if colour in ("colour", "color"):
        mono = False
    elif colour in ("mono", "bw", "blackwhite"):
        mono = True
    else:
        raise ValueError("colour must be 'colour' or 'mono'")

    try:
        copies_n = int(copies)
        if copies_n < 1:
            raise ValueError
    except ValueError:
        raise ValueError("copies must be a positive integer")

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    # sync_playwright() refuses to run on a thread with an active asyncio
    # event loop (which is where FastAPI calls this from), so do the work
    # on a plain worker thread instead.
    with ThreadPoolExecutor(max_workers=1) as executor:
        job = executor.submit(_submit, file, filename, mono, copies_n).result()

    body = {
        "name": job.get("Name", filename),
        "colour": not mono,
        "copies": copies_n,
        "state": job.get("PrintState", "Unknown"),
    }

    return json.dumps(body, indent=2).encode(), "json"
