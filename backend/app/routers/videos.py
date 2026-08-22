from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..errors import YouTubeAuthError, YouTubeQuotaError
from ..models import User
from ..schemas import TrendingVideo
from ..services.youtube_search import discover_videos

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("/trending", response_model=list[TrendingVideo])
def trending_videos(
    keyword: str = Query(default="", max_length=120),
    region: str = Query(default="BR", min_length=2, max_length=2),
    max_results: int = Query(default=12, ge=1, le=25),
    days: int = Query(default=14, ge=1, le=90),
    _user: User = Depends(get_current_user),
):
    try:
        return discover_videos(keyword=keyword, region=region, max_results=max_results, days=days)
    except YouTubeQuotaError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except YouTubeAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
