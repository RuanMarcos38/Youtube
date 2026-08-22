from app.services.seo_service import (
    YOUTUBE_DESCRIPTION_MAX,
    YOUTUBE_TAG_COUNT_MAX,
    YOUTUBE_TAG_TOTAL_MAX,
    YOUTUBE_TITLE_MAX,
    build_publish_metadata,
    normalize_tags,
)


def test_publish_metadata_is_complete_and_within_youtube_limits():
    metadata = build_publish_metadata(
        title="  Como vender mais usando vídeos curtos no YouTube   ",
        description="Aprenda uma estratégia prática para melhorar seus vídeos e alcançar o público certo.",
        copy_text="Comente qual estratégia você vai testar primeiro.",
        tags=["#marketing digital", "youtube shorts", "marketing digital", "vendas online"],
        source_title="Como vender mais com marketing digital",
        hook="A estratégia que muda seus vídeos curtos",
    )

    assert metadata.title
    assert len(metadata.title) <= YOUTUBE_TITLE_MAX
    assert metadata.description
    assert len(metadata.description) <= YOUTUBE_DESCRIPTION_MAX
    assert "#Shorts" in metadata.description
    assert 3 <= len(metadata.tags) <= YOUTUBE_TAG_COUNT_MAX
    assert len(",".join(metadata.tags)) <= YOUTUBE_TAG_TOTAL_MAX + YOUTUBE_TAG_COUNT_MAX
    assert all(not tag.startswith("#") for tag in metadata.tags)
    assert len({tag.casefold() for tag in metadata.tags}) == len(metadata.tags)


def test_metadata_fallback_prevents_empty_publication_fields():
    metadata = build_publish_metadata(
        title="",
        description="",
        copy_text="",
        tags=[],
        source_title="Financiamento imobiliário explicado",
        hook="Entenda como funciona o financiamento",
    )

    assert metadata.title.startswith("Entenda como funciona")
    assert "Confira este trecho" in metadata.description
    assert "#Shorts" in metadata.description
    assert metadata.tags
    assert "YouTube Shorts" in metadata.tags


def test_tags_respect_total_character_budget():
    tags = normalize_tags([f"palavra-chave muito longa {index} " * 4 for index in range(30)])
    assert len(tags) <= YOUTUBE_TAG_COUNT_MAX
    assert sum(len(tag) + (1 if index else 0) for index, tag in enumerate(tags)) <= YOUTUBE_TAG_TOTAL_MAX
