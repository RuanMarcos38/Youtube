from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


YOUTUBE_TITLE_MAX = 100
YOUTUBE_DESCRIPTION_MAX = 5000
YOUTUBE_TAG_COUNT_MAX = 15
YOUTUBE_TAG_TOTAL_MAX = 450

_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "para", "por", "com", "um", "uma",
    "que", "como", "mais", "se", "no", "na", "nos", "nas", "eu", "ele", "ela", "eles", "elas", "isso", "isto",
    "aí", "ai", "é", "eh", "foi", "ser", "ter", "tem", "pra", "pro", "the", "and", "for", "with", "from", "this", "that",
}


@dataclass(frozen=True)
class PublishMetadata:
    title: str
    description: str
    tags: list[str]


def _compact(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_tag(value: str | None) -> str:
    tag = _compact(value).lstrip("#").strip(" ,.;:|/")
    return tag[:60]


def _words(value: str) -> list[str]:
    return [
        word.strip(".,!?;:()[]{}\"'").lower()
        for word in re.findall(r"[\wÀ-ÿ-]+", _compact(value), flags=re.UNICODE)
        if word.strip(".,!?;:()[]{}\"'")
    ]


def _meaningful_words(value: str) -> list[str]:
    return [word for word in _words(value) if len(word) >= 3 and word not in _STOPWORDS]


def _looks_repetitive(value: str) -> bool:
    words = _words(value)
    if len(words) < 4:
        return False
    counts = Counter(words)
    unique_ratio = len(counts) / len(words)
    dominant_ratio = max(counts.values()) / len(words)
    return unique_ratio < 0.45 or dominant_ratio >= 0.5


def _choose_title(title: str, source_title: str, hook: str) -> str:
    candidates = [_compact(title), _compact(hook), _compact(source_title)]
    for candidate in candidates:
        if candidate and not _looks_repetitive(candidate):
            return candidate[:YOUTUBE_TITLE_MAX].rstrip(" -|:,.!")
    for candidate in candidates:
        if candidate:
            return candidate[:YOUTUBE_TITLE_MAX].rstrip(" -|:,.!")
    return "Short em destaque"


def _keyword_fallbacks(source_title: str, hook: str) -> list[str]:
    source = _compact(source_title)
    hook_text = _compact(hook)
    source_words = _meaningful_words(source)
    hook_words = _meaningful_words(hook_text)
    keyword_words = list(dict.fromkeys([*hook_words, *source_words]))

    result: list[str] = []
    if source and not _looks_repetitive(source):
        result.append(source[:60])
    if hook_text and hook_text.casefold() != source.casefold() and not _looks_repetitive(hook_text):
        result.append(hook_text[:60])

    result.extend(keyword_words[:6])
    for index in range(min(4, max(0, len(keyword_words) - 1))):
        phrase = f"{keyword_words[index]} {keyword_words[index + 1]}"
        if len(phrase) <= 60:
            result.append(phrase)

    result.extend(["YouTube Shorts", "Shorts", "vídeo curto"])
    return result


def normalize_tags(tags: list[str] | None, *, source_title: str = "", hook: str = "") -> list[str]:
    candidates = [*(tags or []), *_keyword_fallbacks(source_title, hook)]
    result: list[str] = []
    seen: set[str] = set()
    total = 0

    for raw in candidates:
        tag = _clean_tag(raw)
        if not tag or _looks_repetitive(tag):
            continue
        key = tag.casefold()
        if key in seen:
            continue
        projected = total + len(tag) + (1 if result else 0)
        if projected > YOUTUBE_TAG_TOTAL_MAX:
            continue
        seen.add(key)
        result.append(tag)
        total = projected
        if len(result) >= YOUTUBE_TAG_COUNT_MAX:
            break
    return result


def _hashtags(tags: list[str]) -> list[str]:
    result = ["#Shorts"]
    seen = {"#shorts"}
    for tag in tags:
        slug = re.sub(r"[^\wÀ-ÿ]", "", tag, flags=re.UNICODE)
        if not slug:
            continue
        hashtag = f"#{slug[:35]}"
        key = hashtag.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(hashtag)
        if len(result) >= 4:
            break
    return result


def _description_subject(clean_hook: str, clean_source: str, clean_title: str) -> str:
    for candidate in (clean_hook, clean_source, clean_title):
        if candidate and not _looks_repetitive(candidate):
            return candidate
    return clean_title or "este conteúdo"


def normalize_clip_metadata(
    *,
    title: str | None,
    description: str | None,
    copy_text: str | None,
    tags: list[str] | None,
    source_title: str = "",
    hook: str = "",
) -> tuple[str, str, str, list[str]]:
    clean_hook = _compact(hook)
    clean_source = _compact(source_title)
    clean_title = _choose_title(_compact(title), clean_source, clean_hook)

    normalized_tags = normalize_tags(tags, source_title=clean_source, hook=clean_hook)

    clean_description = str(description or "").strip()
    if not clean_description or _looks_repetitive(clean_description):
        subject = _description_subject(clean_hook, clean_source, clean_title)
        clean_description = f"Confira este trecho sobre {subject}."
    clean_description = clean_description[:4200].rstrip()

    clean_copy = str(copy_text or "").strip()[:500]
    return clean_title, clean_description, clean_copy, normalized_tags


def build_publish_metadata(
    *,
    title: str | None,
    description: str | None,
    copy_text: str | None,
    tags: list[str] | None,
    source_title: str = "",
    hook: str = "",
) -> PublishMetadata:
    clean_title, clean_description, clean_copy, normalized_tags = normalize_clip_metadata(
        title=title,
        description=description,
        copy_text=copy_text,
        tags=tags,
        source_title=source_title,
        hook=hook,
    )

    parts = [clean_description]
    if clean_copy and clean_copy.casefold() not in clean_description.casefold():
        parts.append(clean_copy)

    hashtag_line = " ".join(_hashtags(normalized_tags))
    existing_text = "\n".join(parts).casefold()
    if hashtag_line and hashtag_line.casefold() not in existing_text:
        parts.append(hashtag_line)

    full_description = "\n\n".join(part for part in parts if part).strip()
    full_description = full_description[:YOUTUBE_DESCRIPTION_MAX].rstrip()

    return PublishMetadata(
        title=clean_title,
        description=full_description,
        tags=normalized_tags,
    )
