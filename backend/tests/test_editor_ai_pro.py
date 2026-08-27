from app.services.editor_ai_pro import (
    DEFAULT_EDIT_OPTIONS,
    MotionCue,
    _append_or_replace_track,
    _build_broll_items,
    _fallback_hooks,
    _fallback_motion_cues,
    _micro_captions,
    _normalized_options,
    _zoom_for_clip,
)


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


def test_fallback_motion_cues_prioritize_hook_numbers_and_keywords():
    timeline = _timeline()
    timeline["tracks"][0]["items"].append({"start": 9.0, "end": 10.0, "text": "Foram 3 detalhes importantes", "highlighted_words": ["detalhes"]})

    cues = _fallback_motion_cues(timeline, ["acabamento premium"])

    assert cues
    assert any(cue.emphasis == "hook" for cue in cues)
    assert any(cue.emphasis == "number" for cue in cues)
    assert any(cue.position in {"side_left", "side_right"} for cue in cues)
    assert all(isinstance(cue, MotionCue) for cue in cues)


def test_append_or_replace_track_does_not_duplicate_track():
    timeline = {"tracks": [{"id": "sound-design", "type": "audio_fx", "items": []}]}
    _append_or_replace_track(timeline, {"id": "sound-design", "type": "audio_fx", "items": [{"id": "generated-bed"}]})
    tracks = [track for track in timeline["tracks"] if track["id"] == "sound-design"]
    assert len(tracks) == 1
    assert tracks[0]["items"][0]["id"] == "generated-bed"


def test_micro_captions_break_long_phrase_into_performance_chunks():
    source = [{"start": 0.0, "end": 2.4, "text": "Este produto entrega acabamento premium e muita praticidade", "highlighted_words": ["premium"]}]
    captions = _micro_captions(source, "impact")
    assert len(captions) >= 3
    assert all(len(item["text"].split()) <= 3 for item in captions)
    assert captions[0]["start"] == 0.0
    assert captions[-1]["end"] == 2.4
    assert any("premium" in item["highlighted_words"] for item in captions)


def test_edit_options_are_sanitized_without_touching_credentials():
    project = {"edit_options": {"music_volume": 9, "caption_style": "invalid", "edit_intensity": "maximum"}}
    options = _normalized_options(project)
    assert options["music_volume"] == 0.45
    assert options["caption_style"] == "auto"
    assert options["edit_intensity"] == "maximum"
    assert set(DEFAULT_EDIT_OPTIONS).issubset(options)


def test_maximum_intensity_has_stronger_punch_in():
    balanced = _zoom_for_clip(1, "balanced", False)
    high = _zoom_for_clip(1, "high", False)
    maximum = _zoom_for_clip(1, "maximum", False)
    broll = _zoom_for_clip(1, "high", True)
    assert balanced < high < maximum
    assert broll > high
