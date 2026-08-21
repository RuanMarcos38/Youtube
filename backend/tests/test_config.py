from app.config import Settings


def test_openai_model_env_alias(monkeypatch):
    monkeypatch.delenv("OPENAI_TEXT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")

    settings = Settings(_env_file=None)

    assert settings.openai_text_model == "gpt-4.1"


def test_openai_model_env_alias_has_priority(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "gpt-5")

    settings = Settings(_env_file=None)

    assert settings.openai_text_model == "gpt-4.1"
