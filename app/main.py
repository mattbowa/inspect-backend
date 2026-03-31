import structlog
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.database import init_db
from app.api import scans, reports, history

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="SEO Agent", lifespan=lifespan)

app.include_router(scans.router, prefix="/scans", tags=["scans"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(history.router, prefix="/history", tags=["history"])


@app.get("/health")
def health():
    return {"status": "ok"}
