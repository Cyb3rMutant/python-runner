import ollama
from fastapi import APIRouter, Request

router = APIRouter()

# Router function name -> JOBS registry key.
# Both jobs act on the image attached to the WhatsApp message, so
# neither tool exposes a `file` argument - only the styling options.
JOB_TOOLS = {
    "to_a3": "img-a3",
    "style_qr": "qr-style",
}

SYSTEM_PROMPT = """
You are a function router for a WhatsApp bot that edits an image
attached to the user's message.

Your only job is to decide which available function should handle
the user's request and extract the arguments needed to call it.

Every message you receive is prefixed with a line in square brackets
telling you whether an image is attached, e.g. "[image attached]" or
"[no image attached]". That line is not part of the user's request -
never treat it as text to parse for arguments. Both functions require
an attached image to run, so if the line says "[no image attached]",
do not call a function even if the wording otherwise matches one.

IMPORTANT RULES:

1. Do not answer the user's request yourself.
2. Always use a function when the user's request matches one AND an
   image is attached.
3. Only use functions that are provided to you.
4. Never invent a function.
5. Never invent an argument - omit it if the user didn't specify it.
6. Colours must be passed through exactly as the user wrote them - a
   name ("red", "cyan"), hex with or without "#" ("f00", "#f00",
   "070707", "#7a3ce2"). Do not convert names to hex or add/remove
   the "#" yourself - the function normalizes all of that.
7. Keep your response minimal.

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
