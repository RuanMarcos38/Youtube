from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import settings
from .database import Base, engine
from .routers import clips, jobs, system, videos, youtube_auth


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    settings.data_path.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/media", StaticFiles(directory=str(settings.data_path)), name="media")
app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(videos.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)
app.include_router(clips.router, prefix=settings.api_prefix)
app.include_router(youtube_auth.router, prefix=settings.api_prefix)


@app.get("/")
def root():
    return {"message": settings.app_name, "docs": "/docs"}
