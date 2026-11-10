@echo off
start "Invictus Backend" cmd /k "cd /d %~dp0backend && if not exist .venv python -m venv .venv && call .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000"
timeout /t 2 >nul
start "Invictus Frontend" cmd /k "cd /d %~dp0frontend && npm install && npm run dev"

