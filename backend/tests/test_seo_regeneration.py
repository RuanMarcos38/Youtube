from types import SimpleNamespace

import unittest
from unittest.mock import patch

from app.config import settings
from app.services import seo_ai
from app.services.seo_service import youtube_tag_budget


CONTEXT = dict(
    source_title="Vendas e marketing digital",
    hook="Como melhorar a geração de leads",
    content_text="Uma oferta clara melhora a geração de leads e o funil de vendas. Marketing digital precisa de mensagem e público.",
    current_title="Como melhorar a geração de leads",
    current_description="Uma oferta clara melhora a geração de leads e o funil de vendas.",
    require_ai=True,
)


def package(**overrides):
    return seo_ai.SeoPackage(**{
        "title": "Oferta Clara: o Caminho para Atrair Clientes",
        "description": "Captação de clientes começa com uma mensagem clara para o público certo. Veja a relação entre oferta e funil comercial. Qual ajuste você faria na sua oferta?",
        "tags": [
            {"keyword": term, "relevance_score": 90}
            for term in ["captação de clientes", "oferta comercial", "funil de vendas", "marketing digital", "atrair clientes"]
        ],
        **overrides,
    })


def fake_ai(monkeypatch, responses):
    calls = []
    values = iter(responses)

    class Client:
        def __init__(self, **kwargs):
            self.responses = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def parse(self, **kwargs):
            calls.append(kwargs)
            value = next(values)
            if isinstance(value, Exception):
                raise value
            return SimpleNamespace(output_parsed=value)

    monkeypatch.setattr(settings, "openai_api_key", "test-placeholder")
    monkeypatch.setattr(seo_ai, "OpenAI", Client)
    return calls


class SeoRegenerationTests(unittest.TestCase):
    def setattr(self, target, name, value):
        mocked = patch.object(target, name, value)
        mocked.start()
        self.addCleanup(mocked.stop)

    def test_strict_generation_does_not_claim_local_output_is_ai(self):
        monkeypatch = self
        monkeypatch.setattr(settings, "openai_api_key", "")
        with self.assertRaisesRegex(seo_ai.SeoGenerationError, "chave"):
            seo_ai.build_ai_qualified_seo(**CONTEXT)


    def test_ai_keeps_original_description_and_semantic_tags(self):
        monkeypatch = self
        fake_ai(monkeypatch, [package()])
        result = seo_ai.build_ai_qualified_seo(**CONTEXT)
        assert result.description == package().description
        assert "Captação de Clientes" in result.tags
        assert len(result.tags) == 5
        assert youtube_tag_budget(result.tags) <= 500


    def test_copied_title_gets_one_new_attempt(self):
        monkeypatch = self
        calls = fake_ai(monkeypatch, [package(title=CONTEXT["current_title"]), package()])
        result = seo_ai.build_ai_qualified_seo(**CONTEXT)
        assert len(calls) == 2
        assert result.title != CONTEXT["current_title"]


    def test_repeated_description_is_rejected(self):
        monkeypatch = self
        fake_ai(monkeypatch, [package(description=CONTEXT["current_description"])] * 2)
        with self.assertRaisesRegex(seo_ai.SeoGenerationError, "nova"):
            seo_ai.build_ai_qualified_seo(**CONTEXT)


    def test_provider_error_is_safe_and_does_not_fall_back(self):
        monkeypatch = self
        fake_ai(monkeypatch, [RuntimeError("sensitive-provider-payload")])
        with self.assertRaises(seo_ai.SeoGenerationError) as error:
            seo_ai.build_ai_qualified_seo(**CONTEXT)
        assert "sensitive-provider-payload" not in str(error.exception)


    def test_missing_parsed_response_is_not_success(self):
        monkeypatch = self
        fake_ai(monkeypatch, [None, None])
        with self.assertRaises(seo_ai.SeoGenerationError):
            seo_ai.build_ai_qualified_seo(**CONTEXT)


    def test_budget_and_duplicate_filter(self):
        monkeypatch = self
        tags = [{"keyword": "busca especifica " + str(i) + " sobre marketing digital " + "x" * 20, "relevance_score": 80} for i in range(12)]
        tags.append(tags[0])
        fake_ai(monkeypatch, [package(tags=tags)])
        result = seo_ai.build_ai_qualified_seo(**CONTEXT)
        assert youtube_tag_budget(result.tags) <= 500
        assert len(result.tags) == len(set(result.tags))

    def test_whitespace_output_is_rejected(self):
        fake_ai(self, [package(title="     ")])
        with self.assertRaises(seo_ai.SeoGenerationError):
            seo_ai.build_ai_qualified_seo(**CONTEXT)
