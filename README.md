# TeachOnce

Teach an agent with one video. Record once, automate repeatedly.

## Project Structure

- `backend/` FastAPI skeleton
- `frontend/` Next.js + Tailwind + TypeScript skeleton

## Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate
pip install -r requirements.txt

cp .env.example .env
python -c "from app.models.db import init_db; init_db()"
uvicorn app.main:app --reload --port 8000
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.
