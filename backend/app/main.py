from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from .config import settings
from .routers import admin, auth, billing, clips, diagnostics, editor_ai, jobs, media, publications, system, tiktok_auth, videos, youtube_auth
from .services.bootstrap import ensure_superadmin
from .services.caption_removal_runtime import install_editor_api_caption_queue
from .services.database_bootstrap import initialize_database


# Preserve the existing editor routes and storage. This only makes the current
# "remove captions" action queue a real clean render for direct-upload projects.
install_editor_api_caption_queue(editor_ai)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_path.mkdir(parents=True, exist_ok=True)
    initialize_database()
    ensure_superadmin()
    yield


app = FastAPI(title=settings.app_name, version="2.6.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SQLAlchemyTimeoutError)
async def database_pool_timeout(_: Request, __: SQLAlchemyTimeoutError):
    """Never expose a raw 500 when every SQL connection is momentarily busy."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "O banco está momentaneamente ocupado. Aguarde alguns segundos e tente novamente; nenhuma configuração foi perdida."
        },
    )


app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(billing.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(diagnostics.router, prefix=settings.api_prefix)
app.include_router(videos.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)
app.include_router(clips.router, prefix=settings.api_prefix)
app.include_router(publications.router, prefix=settings.api_prefix)
app.include_router(editor_ai.router, prefix=settings.api_prefix)
app.include_router(media.router, prefix=settings.api_prefix)
app.include_router(youtube_auth.router, prefix=settings.api_prefix)
app.include_router(tiktok_auth.router, prefix=settings.api_prefix)


@app.get("/")
def root():
    return {"message": settings.app_name, "version": "2.6.1", "docs": "/docs"}
