from app.services import youtube_oauth


def test_oauth_state_roundtrip_includes_code_verifier(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_oauth, "STATE_FILE", tmp_path / "oauth_state.json")

    youtube_oauth._write_oauth_state("state-123", "verifier-456")

    assert youtube_oauth._read_oauth_state() == ("state-123", "verifier-456")


def test_oauth_state_legacy_plain_text(tmp_path, monkeypatch):
    state_file = tmp_path / "oauth_state.txt"
    state_file.write_text("legacy-state", encoding="utf-8")
    monkeypatch.setattr(youtube_oauth, "STATE_FILE", state_file)

    assert youtube_oauth._read_oauth_state() == ("legacy-state", None)
