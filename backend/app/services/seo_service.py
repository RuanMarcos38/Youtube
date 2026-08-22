from __future__ import annotations

import re
from dataclasses import dataclass


YOUTUBE_TITLE_MAX = 100
YOUTUBE_DESCRIPTION_MAX = 5000
YOUTUBE_TAG_COUNT_MAX = 15
YOUTUBE_TAG_TOTAL_MAX = 450

_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "para", "por", "com", "um", "uma",
    "que", "como", "mais", "se", "no", "na", "nos", "nas", "the", "and", "for", "with", "from", "this", "that",
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


def _keyword_fallbacks(source_title: str, hook: str) -> list[str]:
    source = _compact(source_title)
    hook_text = _compact(hook)
    words = [
        word.strip(".,!?;:()[]{}\"'").lower()
        for word in re.findall(r"[\wÀ-ÿ-]+", source, flags=re.UNICODE)
    ]
    words = [word for word in words if len(word) >= 4 and word not in _STOPWORDS]

    result: list[str] = []
    if source:
        result.append(source[:60])
    if hook_text and hook_text.lower() != source.lower():
        result.append(hook_text[:60])
    result.extend(words[:5])
    result.extend(["YouTube Shorts", "Shorts", "vídeo curto"])
    return result


def normalize_tags(tags: list[str] | None, *, source_title: str = "", hook: str = "") -> list[str]:
    candidates = [*(tags or []), *_keyword_fallbacks(source_title, hook)]
    result: list[str] = []
    seen: set[str] = set()
    total = 0

    for raw in candidates:
        tag = _clean_tag(raw)
        if not tag:
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
    for tag in tags:
        slug = re.sub(r"[^\wÀ-ÿ]", "", tag, flags=re.UNICODE)
        if not slug or slug.casefold() == "shorts":
            continue
        hashtag = f"#{slug[:35]}"
        if hashtag.casefold() not in {item.casefold() for item in result}:
            result.append(hashtag)
        if len(result) >= 3:
            break
    return result


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
    clean_title = _compact(title) or clean_hook or clean_source or "Short em destaque"
    clean_title = clean_title[:YOUTUBE_TITLE_MAX].rstrip(" -|:,.!")

    normalized_tags = normalize_tags(tags, source_title=clean_source, hook=clean_hook)

    clean_description = str(description or "").strip()
    if not clean_description:
        subject = clean_hook or clean_source or "este conteúdo"
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
    parts.append(" ".join(_hashtags(normalized_tags)))
    full_description = "\n\n".join(part for part in parts if part).strip()
    full_description = full_description[:YOUTUBE_DESCRIPTION_MAX].rstrip()

    return PublishMetadata(
        title=clean_title,
        description=full_description,
        tags=normalized_tags,
    )
