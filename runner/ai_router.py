import json
import math
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

ROUTER_FUNCTIONS = ["to_a3", "style_qr", "set_link", "get_link", "none"]

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

- get_link: Looks up the short link uwe.isoc.link/<ending> and returns
  where it points along with a QR code for it. Arguments: ending
  (required).

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
            "enum": ROUTER_FUNCTIONS,
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


def _chatml_prompt(user_text: str) -> str:
    # Qwen2.5 uses ChatML - mirrors what create_chat_completion renders.
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{user_text}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def _function_confidence(llm: Llama, user_text: str, output: str, chosen: str) -> float | None:
    """Probability the model gave to `chosen` vs the other functions.

    Real logprobs need logits_all=True, which allocates an n_ctx x n_vocab
    float buffer (~1.2GB for Qwen's 150k vocab). Instead, re-feed the prompt
    plus the generated JSON up to the function name's opening quote and read
    the logits for the next token only. The prompt prefix is still in the KV
    cache from the generation, so this is just a handful of tokens to eval.
    Confidence = softmax over the first token of each allowed function name.
    """
    try:
        value_start = output.index(f'"{chosen}"') + 1
        prefix = _chatml_prompt(user_text) + output[:value_start]
        tokens = llm.tokenize(prefix.encode(), add_bos=True, special=True)

        first_tokens = {}
        for name in ROUTER_FUNCTIONS:
            first_tokens[name] = llm.tokenize(name.encode(), add_bos=False, special=False)[0]
        if len(set(first_tokens.values())) != len(first_tokens):
            return None  # names share a first token - can't tell them apart

        # Reuse whatever prefix is already evaluated in the KV cache.
        cached = llm.input_ids[: llm.n_tokens].tolist()
        common = 0
        for a, b in zip(cached, tokens):
            if a != b:
                break
            common += 1
        common = min(common, len(tokens) - 1)  # always eval at least one token
        llm.n_tokens = common
        llm.eval(tokens[common:])

        logits = llm._ctx.get_logits()
        scores = {name: logits[tok] for name, tok in first_tokens.items()}
        top = max(scores.values())
        exps = {name: math.exp(v - top) for name, v in scores.items()}
        return exps[chosen] / sum(exps.values())
    except Exception as exc:  # confidence is best-effort, never block a reply
        print("confidence failed:", exc)
        return None


def _result(function, arguments=None, confidence=None, reason=None) -> dict:
    return {
        "function": function,
        "arguments": arguments or {},
        "confidence": confidence,
        "reason": reason,
    }


def decide_what_to_call(text):
    """Returns {"function", "arguments", "confidence", "reason"}.

    `function` is None when nothing should run, with `reason` saying why.
    """
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

    output = response["choices"][0]["message"]["content"]
    parsed = json.loads(output)

    function_name = parsed.get("function")
    confidence = _function_confidence(llm, masked_text, output, function_name) if function_name else None

    if not function_name or function_name == "none":
        return _result(None, confidence=confidence, reason="that doesn't match anything I can do")

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
        if not ending:
            return _result(None, confidence=confidence, reason=f"{function_name}: no link name given")
        if not re.search(rf"\b{re.escape(ending)}\b", text, re.IGNORECASE):
            return _result(
                None,
                confidence=confidence,
                reason=f"{function_name}: guessed link name '{ending}' isn't in your message",
            )

    if function_name == "set_link":
        url = arguments.get("url")
        if not url or url not in URL_RE.findall(text):
            return _result(None, confidence=confidence, reason="set_link: no url in your message")

    return _result(function_name, arguments, confidence)


@router.post("/ai/decide")
async def ai_decide(request: Request):
    form = await request.form()

    return decide_what_to_call(form.get("q"))
