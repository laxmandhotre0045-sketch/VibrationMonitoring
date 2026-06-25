# How to Start the Platform

## Step 1 — Start PostgreSQL (Docker required)
```
docker-compose up -d
```
- PostgreSQL runs on port 5432
- pgAdmin runs on http://localhost:5050 (admin@vibration.com / admin2024)

## Step 2 — Start Backend
Open a terminal in the `backend/` folder:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- API runs on http://localhost:8000
- API docs at http://localhost:8000/docs

## Step 3 — Start Frontend
Open another terminal in the `frontend/` folder:
```
npm install
npm run dev
```
- App runs on http://localhost:5173

## Step 4 — Open the app
Go to http://localhost:5173
