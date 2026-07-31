FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    lmodern \
    latexmk \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /root/.ssh && \
    ssh-keyscan -t rsa,ed25519 github.com >> /root/.ssh/known_hosts && \
    chmod 600 /root/.ssh/known_hosts

WORKDIR /app

COPY requirements /app/requirements
RUN pip install --no-cache-dir -r requirements

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
