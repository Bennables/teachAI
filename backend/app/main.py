from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_runs import router as runs_router
from app.api.routes_workflows import router as workflows_router

app = FastAPI(title="TeachOnce API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(workflows_router)
app.include_router(runs_router)
