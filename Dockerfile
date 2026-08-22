FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
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
RUN playwright install --with-deps firefox

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
