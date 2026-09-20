from app.routers.vidiq import VidiqChatRequest, _fallback_intent, _tool_args


def test_keyword_question_routes_to_keyword_research():
    payload = VidiqChatRequest(message="Quais palavras-chave para marketing digital têm melhor SEO?")
    intent = _fallback_intent(payload)
    assert intent.tool == "vidiq_keyword_research"
    args = _tool_args(intent, payload)
    assert args["mode"] == "research"
    assert args["country"] == "BR"


def test_title_question_routes_to_short_title_score():
    payload = VidiqChatRequest(message="Pontue o título: Como Vender Mais no YouTube")
    intent = _fallback_intent(payload)
    assert intent.tool == "vidiq_score_title"
    args = _tool_args(intent, payload)
    assert args["type"] == "short"
    assert "Como Vender Mais" in args["title"]


def test_private_analytics_requires_channel():
    payload = VidiqChatRequest(message="Quais são minhas fontes de tráfego?")
    intent = _fallback_intent(payload)
    assert intent.tool == "vidiq_channel_analytics"
