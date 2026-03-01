import asyncio
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocket

from app.api.routes_workflows import get_distill_job

from app.api.routes_parseprompt import router as parseprompt_router

# Load .env from backend directory so OPENAI_API_KEY etc. are set
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from app.api.routes_booking import router as booking_router
from app.api.routes_greenhouse import router as greenhouse_router
from app.api.routes_runs import router as runs_router
from app.api.routes_workflows import router as workflows_router

app = FastAPI(title="TeachOnce API", version="0.1.0")




app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        payload = await websocket.receive_json()
        job_id = payload.get("job_id") if isinstance(payload, dict) else None
        if not isinstance(job_id, str) or not job_id.strip():
            await websocket.send_json(
                {"status": "error", "percent": 100, "message": "Missing required job_id."}
            )
            await websocket.close(code=1008)
            return

        while True:
            job = get_distill_job(job_id)
            if job is None:
                await websocket.send_json(
                    {"status": "error", "percent": 100, "message": f"Job not found: {job_id}"}
                )
                await websocket.close(code=1008)
                return

            await websocket.send_json(job)
            if job.get("status") in {"done", "error"}:
                break
            await asyncio.sleep(0.35)
    finally:
        await websocket.close()




app.include_router(workflows_router)
app.include_router(runs_router)
app.include_router(parseprompt_router)
app.include_router(greenhouse_router)
app.include_router(booking_router)
