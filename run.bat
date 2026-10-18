@echo off
REM Double-click on Windows: installs once, then opens DataLoad
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
pip install -q -r requirements.txt
start "" http://localhost:8000
uvicorn server:app --port 8000
