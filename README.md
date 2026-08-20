# Quiz Management Backend

This is a Python FastAPI starter backend for the Quiz Management and Online Assessment Platform.

## Run locally

```bash
cd quiz_platform_backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `/docs` to use the interactive Swagger API documentation.

## Included

- Student registration and login
- JWT authentication
- Admin-only category, quiz, and question creation
- Published quiz discovery with search and filters
- Quiz attempt creation
- Backend score calculation
- Pass or fail calculation
- Leaderboard endpoint
- SQLite database for local development

Before deployment, move the database URL and JWT secret into environment variables, add migrations, implement refresh tokens, and configure PostgreSQL.
