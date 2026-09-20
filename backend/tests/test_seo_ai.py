from app.config import settings
from app.services.seo_ai import build_ai_qualified_seo


def test_ai_seo_falls_back_safely_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    seo = build_ai_qualified_seo(
        source_title="Vendas e marketing digital",
        hook="Como melhorar a geração de leads",
        content_text=(
            "Uma oferta clara melhora a geração de leads e o funil de vendas. "
            "Marketing digital precisa de mensagem, público e estratégia comercial."
        ),
    )

    assert seo.title
    assert seo.description
    assert seo.tags
    assert all(seo.tag_scores[tag] >= 60 for tag in seo.tags)
