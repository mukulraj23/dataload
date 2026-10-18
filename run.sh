#!/usr/bin/env bash
# Mac/Linux: ./run.sh  then open http://localhost:8000
set -e
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
uvicorn server:app --port 8000
