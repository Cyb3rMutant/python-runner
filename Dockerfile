FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    lmodern \
    latexmk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements /app/requirements
RUN pip install --no-cache-dir -r requirements

# Tiny local model for the AI router (function routing only, no chat) - runs
# in-process via llama-cpp-python instead of a separate multi-GB Ollama
# container. Lives outside /app since dev runs bind-mount the repo over
# /app, which would otherwise shadow it.
RUN mkdir -p /models && \
    curl -fL -o /models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
    https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
