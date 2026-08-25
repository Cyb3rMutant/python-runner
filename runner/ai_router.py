import ollama
from fastapi import APIRouter, Request

router = APIRouter()

# Router function name -> (JOBS registry key, fixed kwargs always passed
# to that job alongside whatever the model extracts). to_a3/style_qr act
# on the image attached to the message, so they don't need fixed kwargs.
# The polr functions share one job with three different `action` values,
# so each gets its own function name with `action` pinned - the model
# only ever has to pick a function and fill in `ending`/`url`.
JOB_TOOLS = {
    "to_a3": ("img-a3", {}),
    "style_qr": ("qr-style", {}),
    "add_link": ("polr", {"action": "add"}),
    "update_link": ("polr", {"action": "force_update"}),
    "get_link": ("polr", {"action": "get"}),
}

# Functions that require an image attached to the message to run.
IMAGE_REQUIRED = {"to_a3", "style_qr"}

SYSTEM_PROMPT = """
You are a function router for a WhatsApp bot that can edit an image
attached to the user's message, or manage short links.

Your only job is to decide which available function should handle
the user's request and extract the arguments needed to call it.

Every message you receive is prefixed with a line in square brackets
telling you whether an image is attached, e.g. "[image attached]" or
"[no image attached]". That line is not part of the user's request -
never treat it as text to parse for arguments.

to_a3 and style_qr require an attached image to run, so if the line
says "[no image attached]", do not call either of them even if the
wording otherwise matches. add_link, update_link, and get_link never
need an image - they act only on the link ending/URL you extract from
the text, so call them regardless of whether an image is attached.

IMPORTANT RULES:

1. Do not answer the user's request yourself.
2. Always use a function when the user's request matches one and any
   image requirement (see above) is satisfied.
3. Only use functions that are provided to you.
4. Never invent a function.
5. Never invent an argument - omit it if the user didn't specify it.
6. Colours must be passed through exactly as the user wrote them - a
   name ("red", "cyan"), hex with or without "#" ("f00", "#f00",
   "070707", "#7a3ce2"). Do not convert names to hex or add/remove
   the "#" yourself - the function normalizes all of that.
7. add_link is for a brand new ending. update_link is for an ending
   that already exists and should now point somewhere else - use it
   whenever the user says "change"/"update"/"redirect"/"overwrite" an
   existing link. Never call add_link when the user is asking to
   change where an ending already points.
8. Keep your response minimal.

Examples:

User: "[image attached]\ncan you convert this to a3"
→ call to_a3

User: "[image attached]\nneed this in a3"
→ call to_a3

User: "[image attached]\nneed this qr with cyan and red"
→ call style_qr with fg="cyan", bg="red"

User: "[image attached]\nchange the foreground in this qr to 070707 and background to 7a3ce2"
→ call style_qr with fg="070707", bg="7a3ce2"

User: "[no image attached]\nconvert this to a3"
→ do not call a function

User: "[no image attached]\nmake a link called yt that goes to https://youtube.com"
→ call add_link with ending="yt", url="https://youtube.com"

User: "[no image attached]\nyt should now point to https://youtu.be/dQw4w9WgXcQ instead"
→ call update_link with ending="yt", url="https://youtu.be/dQw4w9WgXcQ"

User: "[no image attached]\nwhere does yt go"
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
            "name": "add_link",
            "description": (
                "Creates a brand new short link at uwe.isoc.link/<ending> "
                "pointing to a URL. Fails if that ending is already taken - "
                "use update_link instead when the ending already exists. "
                "Returns a QR code for the new short link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ending": {
                        "type": "string",
                        "description": "The short link ending to create, e.g. 'yt' for uwe.isoc.link/yt.",
                    },
                    "url": {
                        "type": "string",
                        "description": "The destination URL the new short link should point to.",
                    },
                },
                "required": ["ending", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_link",
            "description": (
                "Overwrites an existing short link at uwe.isoc.link/<ending> "
                "so it points to a new URL. Use this instead of add_link "
                "whenever the ending already exists and should now point "
                "somewhere else. Returns a QR code for the short link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ending": {
                        "type": "string",
                        "description": "The existing short link ending to update, e.g. 'yt' for uwe.isoc.link/yt.",
                    },
                    "url": {
                        "type": "string",
                        "description": "The new destination URL the short link should point to.",
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
                "Looks up where the short link uwe.isoc.link/<ending> "
                "currently points, and returns a QR code for it."
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


def decide_what_to_call(text, image_attached: bool):
    tag = "[image attached]" if image_attached else "[no image attached]"

    response = ollama.chat(
        model="qwen3:0.6b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{tag}\n{text}"},
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

    image_attached = form.get("image_attached", "true").strip().lower() == "true"
    return decide_what_to_call(form.get("q"), image_attached)
