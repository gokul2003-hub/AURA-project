# AURA Backend — Corrected Complete Package

This package contains the corrected AURA backend with the requested WARN/ALLOW calibration and working Human Review decisions.

Startup command:

    cd path
    conda activate toxic_ai
    python -m uvicorn main:app --reload

`main.py` is included at the backend root and exposes the FastAPI object as `app`.

## Files
- `main.py` — Uvicorn entry point.
- `backend.py` — AURA API, authentication, moderation engine, SQLite persistence and admin endpoints.
- `requirements.txt` — only the packages required by this local backend.
- `.env.example` — local configuration reference.
- `start_backend.bat` — Windows one-click starter.

## Start
```text
cd C:\Users\Win\Desktop\TOXIC ADVANCED\BACKEND
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Backend: http://127.0.0.1:8000
Health: http://127.0.0.1:8000/health

## Default admin
Username: `admin`
Password: `Admin@1234`

Normal users can be created through the frontend.

## Main API
- POST `/auth/login`
- POST `/auth/register`
- POST `/moderate`
- GET `/history`
- GET `/comments/me`
- GET `/admin/overview`
- GET `/admin/comments`
- GET `/admin/human-review`
- POST `/admin/human-review/{id}`
- GET `/admin/users`
- POST `/admin/block-user`

The API returns both the canonical fields and compatibility aliases used by the AURA Streamlit frontend, including `risk_score`, `risk.overall`, `moderation.action`, `probabilities`, `confidence`, `uncertainty`, `explainable_ai`, and `publication`.
