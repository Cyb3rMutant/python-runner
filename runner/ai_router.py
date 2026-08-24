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

IMPORTANT RULES:

1. Do not answer the user's request yourself.
2. Always use a function when the user's request matches one.
3. Only use functions that are provided to you.
4. Never invent a function.
5. Never invent an argument - omit it if the user didn't specify it.
6. Colours must always be extracted as 6-digit hex codes with no
   leading "#" (e.g. "cyan" -> "00ffff", "red" -> "ff0000",
   "070707" -> "070707").
7. Keep your response minimal.

Examples:

User: "can you convert this image to a3"
→ call to_a3

User: "need this image in a3"
→ call to_a3

User: "need this qr with cyan and red"
→ call style_qr with fg="00ffff", bg="ff0000"

User: "change the foreground in this qr to 070707 and background to 7a3ce2"
→ call style_qr with fg="070707", bg="7a3ce2"

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
                        "description": "Foreground (module) colour as a 6-digit hex code, or 'transparent'.",
                    },
                    "bg": {
                        "type": "string",
                        "description": "Background colour as a 6-digit hex code, or 'transparent'.",
                    },
                },
                "required": [],
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
