import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from api.config import settings
from api.database import Base, engine
from api.jobs.overdue import overdue_worker
from api.middlewares.security_headers import SecurityHeadersMiddleware
from api.models import entities as _entities
from api.routes import auth, operations, resources

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    worker = asyncio.create_task(overdue_worker())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="API for university laboratory equipment lending, returns, and maintenance.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    logger.info("Database constraint rejected request: %s", exc.orig)
    return JSONResponse(status_code=409, content={"detail": "A unique or relational constraint was violated"})


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(resources.router, prefix="/api/v1")
app.include_router(operations.router, prefix="/api/v1")
