#!/usr/bin/env bash
set -euo pipefail

cd /app

exec uvicorn runner.app:app --host 0.0.0.0 --port 8080 --reload
