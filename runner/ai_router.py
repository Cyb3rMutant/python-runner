import json
import os
import re

from fastapi import APIRouter, Request
from llama_cpp import Llama, LlamaGrammar

URL_RE = re.compile(r"https?://\S+")

router = APIRouter()

# Lives outside /app - see Dockerfile comment on the model download step.
MODEL_PATH = os.environ.get(
    "ROUTER_MODEL_PATH", "/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"
)

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

Any url in the message has already been replaced with the placeholder
<URL> - if set_link applies, just echo <URL> back as the url argument.

Respond with ONLY a JSON object of this shape, nothing else:
{"function": "<name>", "arguments": {...}}

Available functions:

- to_a3: Converts the attached image into an A3-sized PDF, scaled to fit
  and centered on the page. Use for requests to resize, print, or
  convert an image to A3. No arguments.

- style_qr: Recolours the QR code in the attached image. Use for
  requests to change a QR code's colours, foreground, or background.
  Arguments: fg, bg (each optional).

- set_link: Points the short link uwe.isoc.link/<ending> at a URL -
  creates it if that ending doesn't exist yet, or overwrites it if it
  does. Use for any request to make, change, or redirect a short link,
  whether or not it already exists. Returns a QR code for the short
  link. Arguments: ending, url (both required).

- get_link: Confirms the short link uwe.isoc.link/<ending> exists and
  returns a QR code for it. Does not reveal the destination URL as
  text. Arguments: ending (required).

- none: Use this if the request doesn't match any function above. No
  arguments.

IMPORTANT RULES:

1. Do not answer the user's request yourself.
2. Only use functions listed above. Never invent a function.
3. Never invent an argument - omit it if the user didn't specify it.
4. Colours must be passed through exactly as the user wrote them - a
   name ("red", "cyan"), hex with or without "#" ("f00", "#f00",
   "070707", "#7a3ce2"). Do not convert names to hex or add/remove
   the "#" yourself - the function normalizes all of that.
5. `ending` is the short link's own name (e.g. "yt" in "yt should
   point to <URL>").
6. Output ONLY the JSON object. No explanation, no extra text.

Examples:

User: "can you convert this to a3"
{"function": "to_a3", "arguments": {}}

User: "need this qr with cyan and red"
{"function": "style_qr", "arguments": {"fg": "cyan", "bg": "red"}}

User: "change the foreground in this qr to 070707 and background to 7a3ce2"
{"function": "style_qr", "arguments": {"fg": "070707", "bg": "7a3ce2"}}

User: "make a link called docs that goes to <URL>"
{"function": "set_link", "arguments": {"ending": "docs", "url": "<URL>"}}

User: "docs should now point to <URL> instead"
{"function": "set_link", "arguments": {"ending": "docs", "url": "<URL>"}}

User: "where does menu go"
{"function": "get_link", "arguments": {"ending": "menu"}}

User: "what does menu point to"
{"function": "get_link", "arguments": {"ending": "menu"}}

User: "check the menu link still works"
{"function": "get_link", "arguments": {"ending": "menu"}}

User: "what's the weather like"
{"function": "none", "arguments": {}}
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "function": {
            "type": "string",
            "enum": ["to_a3", "style_qr", "set_link", "get_link", "none"],
        },
        "arguments": {
            "type": "object",
            "properties": {
                "fg": {"type": "string"},
                "bg": {"type": "string"},
                "ending": {"type": "string"},
                "url": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    "required": ["function", "arguments"],
    "additionalProperties": False,
}

# Lazily loaded so importing this module (e.g. for the job registry) doesn't
# pay the cost of loading the model until a request actually needs it.
_llm: Llama | None = None


def _get_llm() -> Llama:
    global _llm
    if _llm is None:
        _llm = Llama(model_path=MODEL_PATH, n_ctx=2048, n_threads=os.cpu_count(), verbose=False)
    return _llm


def decide_what_to_call(text):
    llm = _get_llm()

    # A model this small tends to fixate on the tokens inside an interesting
    # (or well-known) url and copy from there instead of correctly picking
    # out the link's own name elsewhere in the sentence. Mask any url out of
    # what the model sees so it has nothing to copy from but the actual
    # ending, then splice the real url back in afterwards.
    urls = URL_RE.findall(text)
    masked_text = text.replace(urls[0], "<URL>", 1) if urls else text

    # A fresh LlamaGrammar per call - the grammar object tracks parse state
    # as it constrains generation, and reusing one across calls carries that
    # state into the next completion, corrupting it.
    grammar = LlamaGrammar.from_json_schema(json.dumps(RESPONSE_SCHEMA))

    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": masked_text},
        ],
        grammar=grammar,
        temperature=0,
    )

    parsed = json.loads(response["choices"][0]["message"]["content"])

    function_name = parsed.get("function")
    if not function_name or function_name == "none":
        return None

    arguments = {k: v for k, v in parsed.get("arguments", {}).items() if v}
    if function_name == "set_link" and urls:
        arguments["url"] = urls[0]

    # A model this small will occasionally invent a plausible-looking
    # ending/url instead of admitting the user didn't give one - usually
    # one copied straight from these very few-shot examples. Since
    # set_link/get_link act on a real link, refuse rather than risk
    # silently touching the wrong one (or, worse, repointing it to a
    # hallucinated url) on a value that isn't actually in the message.
    if function_name in ("set_link", "get_link"):
        ending = arguments.get("ending")
        if not ending or not re.search(rf"\b{re.escape(ending)}\b", text, re.IGNORECASE):
            return None

    if function_name == "set_link":
        url = arguments.get("url")
        if not url or url not in URL_RE.findall(text):
            return None

    return {"function": function_name, "arguments": arguments}


@router.post("/ai/decide")
async def ai_decide(request: Request):
    form = await request.form()

    return decide_what_to_call(form.get("q"))
