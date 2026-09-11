from app.services.seo_quality import build_qualified_local_seo, clip_transcript_text


def test_clip_transcript_uses_only_current_short_window():
    segments = [
        {"start": 0.0, "end": 8.0, "text": "Introdução fora do corte."},
        {"start": 10.0, "end": 18.0, "text": "O erro mais comum no marketing digital é anunciar sem entender o cliente."},
        {"start": 18.0, "end": 28.0, "text": "Uma oferta clara melhora a intenção de compra e a qualidade dos leads."},
        {"start": 40.0, "end": 50.0, "text": "Conclusão fora do corte."},
    ]

    text = clip_transcript_text(segments, 10.0, 30.0)

    assert "erro mais comum" in text
    assert "oferta clara" in text
    assert "Introdução fora" not in text
    assert "Conclusão fora" not in text


def test_generic_local_metadata_becomes_unique_and_content_specific():
    content = (
        "O erro mais comum no marketing digital é anunciar sem entender o cliente. "
        "Uma oferta clara melhora a intenção de compra e a qualidade dos leads. "
        "Antes de aumentar o orçamento, revise a mensagem e o público da campanha."
    )

    seo = build_qualified_local_seo(
        source_title="Estratégias de marketing digital para empresas",
        hook="O erro mais comum no marketing digital",
        content_text=content,
        current_title="O erro mais comum no marketing digital",
        current_description=(
            "Trecho selecionado automaticamente de Estratégias de marketing digital para empresas. "
            "O erro mais comum no marketing digital"
        ),
        current_tags=[],
    )

    assert seo.title
    assert len(seo.title) <= 100
    assert "Trecho selecionado automaticamente" not in seo.description
    assert "oferta clara" in seo.description
    assert len(seo.tags) >= 8
    assert len(seo.tags) <= 15
    assert any("marketing" in tag.lower() for tag in seo.tags)
    assert any("cliente" in tag.lower() or "oferta" in tag.lower() for tag in seo.tags)


def test_existing_specific_description_is_preserved():
    description = (
        "Entenda por que uma oferta clara pode melhorar a qualidade dos leads antes de aumentar o orçamento. "
        "O corte mostra como mensagem, público e intenção de compra se conectam na campanha."
    )

    seo = build_qualified_local_seo(
        source_title="Marketing e vendas",
        hook="Como melhorar a qualidade dos leads",
        content_text="Uma oferta clara ajuda o cliente a entender a proposta antes de clicar no anúncio.",
        current_title="Como melhorar a qualidade dos leads",
        current_description=description,
        current_tags=["qualidade dos leads", "oferta clara", "marketing digital"],
    )

    assert seo.description == description
    assert seo.tags[0] == "qualidade dos leads"
