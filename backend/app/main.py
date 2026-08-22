from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .routers import admin, auth, billing, clips, jobs, media, system, videos, youtube_auth
from .services.bootstrap import ensure_superadmin
from .services.database_bootstrap import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_path.mkdir(parents=True, exist_ok=True)
    initialize_database()
    ensure_superadmin()
    yield


app = FastAPI(title=settings.app_name, version="2.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(billing.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(videos.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)
app.include_router(clips.router, prefix=settings.api_prefix)
app.include_router(media.router, prefix=settings.api_prefix)
app.include_router(youtube_auth.router, prefix=settings.api_prefix)


@app.get("/")
def root():
    return {"message": settings.app_name, "version": "2.2.0", "docs": "/docs"}
