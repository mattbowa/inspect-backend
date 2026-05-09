import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.api import scans, reports, history, billing, contact
from app.config import settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="SEO Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scans.router, prefix="/scans", tags=["scans"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(history.router, prefix="/history", tags=["history"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(contact.router, prefix="/contact", tags=["contact"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def config():
    return {"free_page_limit": settings.free_page_limit}
