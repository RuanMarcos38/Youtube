from __future__ import annotations

import json
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..config import settings
from ..models import User
from ..services.vidiq_mcp import VidiqMcpError, call_vidiq_tool, vidiq_configured


router = APIRouter(prefix="/vidiq", tags=["vidiq"])


VidiqTool = Literal[
    "vidiq_keyword_research",
    "vidiq_score_title",
    "vidiq_channel_stats",
    "vidiq_video_stats",
    "vidiq_trending_videos",
    "vidiq_channel_analytics",
    "vidiq_balance",
    "vidiq_user_channels",
]


class VidiqChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    channel_id: str | None = Field(default=None, max_length=200)
    video_id: str | None = Field(default=None, max_length=500)


class VidiqIntent(BaseModel):
    tool: VidiqTool
    query: str = ""
    title: str = ""
    channel_id: str = ""
    video_id: str = ""
    report: Literal[
        "top_videos",
        "traffic_sources",
        "audience_demographics",
        "audience_geography",
        "revenue_report",
        "shorts_vs_longform_split",
    ] = "top_videos"


def _fallback_intent(payload: VidiqChatRequest) -> VidiqIntent:
    message = payload.message.strip()
    lowered = message.casefold()
    if "crédito" in lowered or "credit" in lowered:
        return VidiqIntent(tool="vidiq_balance")
    if "meus canais" in lowered or "canal conectado" in lowered:
        return VidiqIntent(tool="vidiq_user_channels")
    if "tend" in lowered or "viral" in lowered or "em alta" in lowered:
        return VidiqIntent(tool="vidiq_trending_videos", query=message)
    if "título" in lowered or "titulo" in lowered or "score" in lowered:
        title = re.sub(r"^(avalie|analise|score|pontue)\s+(o\s+)?(título|titulo)\s*[:\-]?\s*", "", message, flags=re.I)
        return VidiqIntent(tool="vidiq_score_title", title=title or message, video_id=payload.video_id or "", channel_id=payload.channel_id or "")
    if "palavra" in lowered or "keyword" in lowered or "seo" in lowered or "busca" in lowered:
        return VidiqIntent(tool="vidiq_keyword_research", query=message)
    if "receita" in lowered or "revenue" in lowered:
        return VidiqIntent(tool="vidiq_channel_analytics", channel_id=payload.channel_id or "", report="revenue_report")
    if "tráfego" in lowered or "trafego" in lowered:
        return VidiqIntent(tool="vidiq_channel_analytics", channel_id=payload.channel_id or "", report="traffic_sources")
    if "geografia" in lowered or "país" in lowered or "pais" in lowered:
        return VidiqIntent(tool="vidiq_channel_analytics", channel_id=payload.channel_id or "", report="audience_geography")
    if "vídeo" in lowered or "video" in lowered:
        return VidiqIntent(tool="vidiq_video_stats", video_id=payload.video_id or message)
    return VidiqIntent(tool="vidiq_channel_stats", channel_id=payload.channel_id or message)


def _ai_intent(payload: VidiqChatRequest) -> VidiqIntent:
    if not settings.openai_api_key:
        return _fallback_intent(payload)
    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "Você roteia perguntas de um painel de YouTube para UMA ferramenta vidIQ. "
        "Escolha keyword_research para SEO/palavras-chave; score_title para pontuar título; "
        "channel_stats para inscritos/views/crescimento público; video_stats para desempenho histórico de um vídeo; "
        "trending_videos para tendências/virais; channel_analytics para dados privados do canal próprio como top vídeos, "
        "fontes de tráfego, demografia, geografia, receita ou Shorts vs longos; balance para créditos; user_channels para canais conectados. "
        "Não invente IDs. Use channel_id/video_id fornecidos quando existirem. "
        "Para keyword query extraia apenas o tema principal; para title extraia somente o título a pontuar."
    )
    try:
        response = client.responses.parse(
            model=settings.openai_text_model,
            input=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": payload.message,
                            "channel_id": payload.channel_id or "",
                            "video_id": payload.video_id or "",
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=VidiqIntent,
        )
        return response.output_parsed or _fallback_intent(payload)
    except Exception:
        return _fallback_intent(payload)


def _tool_args(intent: VidiqIntent, payload: VidiqChatRequest) -> dict[str, Any]:
    channel_id = (intent.channel_id or payload.channel_id or "").strip()
    video_id = (intent.video_id or payload.video_id or "").strip()

    if intent.tool == "vidiq_keyword_research":
        query = (intent.query or payload.message).strip()
        return {"mode": "research", "keyword": query[:150], "includeRelated": True, "country": "BR"}
    if intent.tool == "vidiq_score_title":
        title = (intent.title or payload.message).strip()
        args: dict[str, Any] = {"title": title[:500], "type": "short"}
        if video_id:
            args["videoId"] = video_id
        if channel_id:
            args["channelId"] = channel_id
        return args
    if intent.tool == "vidiq_channel_stats":
        if not channel_id:
            raise ValueError("Informe o ID ou @handle do canal.")
        return {"channelId": channel_id}
    if intent.tool == "vidiq_video_stats":
        if not video_id:
            raise ValueError("Informe o ID ou URL do vídeo.")
        return {"videoId": video_id, "granularity": "daily", "order": "desc"}
    if intent.tool == "vidiq_trending_videos":
        query = (intent.query or payload.message).strip()
        return {
            "videoFormat": "short",
            "titleQuery": query[:500],
            "videoTitleLanguage": "pt",
            "channelCountry": "BR",
            "sortBy": "vph",
            "limit": 10,
        }
    if intent.tool == "vidiq_channel_analytics":
        if not channel_id:
            raise ValueError("Selecione ou informe o canal conectado ao vidIQ.")
        return {"channelId": channel_id, "report": intent.report}
    return {}


def _fallback_answer(tool: str, data: dict[str, Any]) -> str:
    if tool == "vidiq_score_title" and "score" in data:
        return f"Pontuação vidIQ do título: {data['score']}/100."
    if tool == "vidiq_balance":
        credits = data.get("totalCredits")
        return f"Créditos vidIQ disponíveis: {credits}." if credits is not None else "Saldo do vidIQ carregado."
    return "Métricas do vidIQ carregadas com sucesso. Os dados completos estão disponíveis abaixo."


def _summarize(message: str, tool: str, data: dict[str, Any]) -> str:
    if not settings.openai_api_key:
        return _fallback_answer(tool, data)
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.responses.create(
            model=settings.openai_text_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Você é o analista de YouTube do ShortsFlow AI. Responda em português do Brasil. "
                        "Use somente os dados reais do vidIQ fornecidos. Seja direto, destaque números importantes, "
                        "explique o que significam e indique próximos passos práticos sem inventar métricas."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Pergunta: {message}\nFerramenta: {tool}\n"
                        f"Dados vidIQ: {json.dumps(data, ensure_ascii=False)[:18000]}"
                    ),
                },
            ],
        )
        text = getattr(response, "output_text", "") or ""
        return text.strip() or _fallback_answer(tool, data)
    except Exception:
        return _fallback_answer(tool, data)


@router.get("/status")
async def vidiq_status(user: User = Depends(get_current_user)):
    _ = user
    if not vidiq_configured():
        return {
            "configured": False,
            "connected": False,
            "credits": None,
            "channels": [],
            "message": "Adicione VIDIQ_MCP_API_KEY nos segredos do EasyPanel para ativar o vidIQ no ShortsFlow.",
        }
    try:
        balance = await call_vidiq_tool("vidiq_balance", {})
        channels = await call_vidiq_tool("vidiq_user_channels", {})
        return {
            "configured": True,
            "connected": True,
            "credits": balance,
            "channels": channels.get("channels") or [],
            "authenticated_as": channels.get("authenticatedAs"),
            "message": "",
        }
    except VidiqMcpError as exc:
        return {
            "configured": True,
            "connected": False,
            "credits": None,
            "channels": [],
            "message": str(exc),
        }


@router.post("/chat")
async def vidiq_chat(payload: VidiqChatRequest, user: User = Depends(get_current_user)):
    _ = user
    if not vidiq_configured():
        raise HTTPException(
            status_code=503,
            detail="vidIQ ainda não está configurado no EasyPanel. Defina VIDIQ_MCP_API_KEY como segredo de runtime.",
        )
    intent = _ai_intent(payload)
    try:
        args = _tool_args(intent, payload)
        data = await call_vidiq_tool(intent.tool, args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VidiqMcpError as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar vidIQ: {exc}") from exc

    return {
        "answer": _summarize(payload.message, intent.tool, data),
        "tool": intent.tool,
        "data": data,
    }
