from app.services.editor_ai_pro import _append_or_replace_track, _build_broll_items, _fallback_hooks


def _timeline():
    return {
        "duration": 12.0,
        "tracks": [
            {
                "id": "captions",
                "type": "captions",
                "items": [
                    {"start": 0.0, "end": 1.2, "text": "Veja este produto em ação"},
                    {"start": 3.0, "end": 4.1, "text": "O acabamento premium chama atenção"},
                    {"start": 7.0, "end": 8.0, "text": "Agora veja o detalhe"},
                ],
            }
        ],
    }


def test_build_broll_items_uses_confirmed_source_rights():
    items = _build_broll_items(_timeline(), ["acabamento premium", "detalhe"])
    assert items
    assert all(item["source_type"] == "source_derived" for item in items)
    assert all(item["rights"] == "user_confirmed_source" for item in items)
    assert all(item["timeline_out"] > item["timeline_in"] for item in items)


def test_fallback_hooks_returns_three_short_variants():
    project = {"original_filename": "produto-demo.mp4"}
    hooks = _fallback_hooks(project, _timeline())
    assert len(hooks) == 3
    assert len({hook.lower() for hook in hooks}) == 3
    assert all(len(hook) <= 64 for hook in hooks)


def test_append_or_replace_track_does_not_duplicate_track():
    timeline = {"tracks": [{"id": "sound-design", "type": "audio_fx", "items": []}]}
    _append_or_replace_track(
        timeline,
        {"id": "sound-design", "type": "audio_fx", "items": [{"id": "generated-bed"}]},
    )
    tracks = [track for track in timeline["tracks"] if track["id"] == "sound-design"]
    assert len(tracks) == 1
    assert tracks[0]["items"][0]["id"] == "generated-bed"
