import ollama
from fastapi import APIRouter, Request

router = APIRouter()

# Router function name -> (JOBS registry key, fixed kwargs always passed
# to that job alongside whatever the model extracts). to_a3/style_qr act
# on the image attached to the message, so they don't need fixed kwargs.
# set_link/get_link share one job with two different `action` values, so
# each gets its own function name with `action` pinned - the model only
# ever has to pick a function and fill in `ending`/`url`.
JOB_TOOLS = {
    "to_a3": ("img-a3", {}),
    "style_qr": ("qr-style", {}),
    "set_link": ("polr", {"action": "set"}),
    "get_link": ("polr", {"action": "get"}),
}

# Functions that require an image attached to the message to run.
IMAGE_REQUIRED = {"to_a3", "style_qr"}

SYSTEM_PROMPT = """
You are a function router for a WhatsApp bot that can edit an image
attached to the user's message, or manage short links.

Your only job is to decide which available function should handle
the user's request and extract the arguments needed to call it.
Whether an image is actually attached is checked separately, after
your decision - just match the wording to a function.

IMPORTANT RULES:

1. Do not answer the user's request yourself.
2. Always use a function when the user's request matches one.
3. Only use functions that are provided to you.
4. Never invent a function.
5. Never invent an argument - omit it if the user didn't specify it.
6. Colours must be passed through exactly as the user wrote them - a
   name ("red", "cyan"), hex with or without "#" ("f00", "#f00",
   "070707", "#7a3ce2"). Do not convert names to hex or add/remove
   the "#" yourself - the function normalizes all of that.
7. Keep your response minimal.

Examples:

User: "can you convert this to a3"
→ call to_a3

User: "need this in a3"
→ call to_a3

User: "need this qr with cyan and red"
→ call style_qr with fg="cyan", bg="red"

User: "change the foreground in this qr to 070707 and background to 7a3ce2"
→ call style_qr with fg="070707", bg="7a3ce2"

User: "make a link called yt that goes to https://youtube.com"
→ call set_link with ending="yt", url="https://youtube.com"

User: "yt should now point to https://youtu.be/dQw4w9WgXcQ instead"
→ call set_link with ending="yt", url="https://youtu.be/dQw4w9WgXcQ"

User: "where does yt go"
→ call get_link with ending="yt"

Do not explain your decision.
Do not return a normal conversational answer.
Select the appropriate function and provide its arguments.
"""

tools = [
    {
        "type": "function",
        "function": {
            "name": "to_a3",
            "description": (
                "Converts the attached image into an A3-sized PDF, scaled "
                "to fit and centered on the page. Use this when the user "
                "wants the image resized, printed, or converted to A3."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "style_qr",
            "description": (
                "Recolours the QR code in the attached image. Use this "
                "when the user wants a QR code's colours, foreground, or "
                "background changed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fg": {
                        "type": "string",
                        "description": "Foreground (module) colour, exactly as the user wrote it: a colour name, hex (3/6-digit, with or without '#'), or 'transparent'.",
                    },
                    "bg": {
                        "type": "string",
                        "description": "Background colour, exactly as the user wrote it: a colour name, hex (3/6-digit, with or without '#'), or 'transparent'.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_link",
            "description": (
                "Points the short link uwe.isoc.link/<ending> at a URL - "
                "creates it if that ending doesn't exist yet, or overwrites "
                "it if it does. Use this for any request to make, change, "
                "or redirect a short link, whether or not it already exists. "
                "Returns a QR code for the short link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ending": {
                        "type": "string",
                        "description": "The short link ending, e.g. 'yt' for uwe.isoc.link/yt.",
                    },
                    "url": {
                        "type": "string",
                        "description": "The destination URL the short link should point to.",
                    },
                },
                "required": ["ending", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_link",
            "description": (
                "Confirms the short link uwe.isoc.link/<ending> exists and "
                "returns a QR code for it. Fails if that ending doesn't "
                "exist. Does not reveal the destination URL as text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ending": {
                        "type": "string",
                        "description": "The short link ending to look up, e.g. 'yt' for uwe.isoc.link/yt.",
                    },
                },
                "required": ["ending"],
            },
        },
    },
]


def decide_what_to_call(text):
    response = ollama.chat(
        model="qwen3:0.6b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        tools=tools,
        think=False,
    )

    calls = response.message.tool_calls

    if not calls:
        return None

    call = calls[0]

    return {
        "function": call.function.name,
        "arguments": call.function.arguments,
    }


@router.post("/ai/decide")
async def ai_decide(request: Request):
    form = await request.form()

    return decide_what_to_call(form.get("q"))
