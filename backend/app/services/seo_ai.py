from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import settings
from .seo_quality import QualifiedSeo, build_qualified_local_seo


class SeoTagCandidate(BaseModel):
    keyword: str = Field(min_length=2, max_length=70)
    relevance_score: int = Field(ge=60, le=100)


class SeoPackage(BaseModel):
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=30, max_length=1800)
    tags: list[SeoTagCandidate] = Field(default_factory=list, min_length=8, max_length=40)


def build_ai_qualified_seo(
    *,
    source_title: str,
    hook: str,
    content_text: str,
) -> QualifiedSeo:
    """Generate SEO with OpenAI, then enforce the deterministic 60+ relevance gate.

    If OpenAI is unavailable, the existing local SEO builder remains fully
    functional so the publication flow is never broken.
    """

    local = build_qualified_local_seo(
        source_title=source_title,
        hook=hook,
        content_text=content_text,
        current_title=hook or source_title,
        current_description="",
        current_tags=[],
    )
    if not settings.openai_api_key:
        return local

    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "Você é um estrategista sênior de SEO para YouTube Shorts. "
        "Use SOMENTE o conteúdo real fornecido. Gere metadados em português do Brasil, sem inventar fatos. "
        "Título: até 100 caracteres, forte para busca e clique, com as palavras relevantes iniciando em maiúscula, "
        "sem caixa alta excessiva e sem clickbait enganoso. "
        "Descrição: natural, clara, com a palavra-chave principal logo no início, contexto objetivo e CTA curto. "
        "Tags: gere entre 18 e 40 termos SEM #. Misture palavra-chave principal, variações semânticas e long tails. "
        "Cada tag deve ter relevance_score de 60 a 100 apenas quando estiver diretamente relacionada ao conteúdo. "
        "Não use nomes de celebridades, tendências ou termos de alto volume que não apareçam ou não sejam sustentados pelo vídeo. "
        "O relevance_score é uma estimativa interna de relevância, não declare que é uma pontuação oficial do vidIQ."
    )
    user = (
        f"Título do vídeo de origem: {source_title}\n"
        f"Gancho do Short: {hook}\n\n"
        f"Conteúdo real do Short:\n{content_text[:12000]}"
    )

    try:
        response = client.responses.parse(
            model=settings.openai_text_model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text_format=SeoPackage,
        )
        package = response.output_parsed
        if not package:
            return local

        ai_tags = [
            item.keyword
            for item in package.tags
            if int(item.relevance_score) >= 60
        ]
        qualified = build_qualified_local_seo(
            source_title=source_title,
            hook=hook,
            content_text=content_text,
            current_title=package.title,
            current_description=package.description,
            current_tags=ai_tags,
        )
        if len(qualified.tags) < 8:
            return local
        return qualified
    except Exception:
        return local
