@echo off
echo Setting up AI Vibration Intelligence Platform - Backend
echo =========================================================

REM Create virtual environment
python -m venv .venv
call .venv\Scripts\activate.bat

REM Install dependencies
pip install -r requirements.txt

REM Copy env file
if not exist ".env" (
    copy ..\\.env .env
)

REM Run migrations
alembic upgrade head

echo.
echo Backend setup complete!
echo Starting server on http://localhost:8000
echo API docs at http://localhost:8000/docs
echo.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
