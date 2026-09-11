from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .seo_service import normalize_tags


@dataclass(frozen=True)
class QualifiedSeo:
    title: str
    description: str
    tags: list[str]


_STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "para", "por", "com", "um", "uma",
    "que", "como", "mais", "se", "no", "na", "nos", "nas", "eu", "ele", "ela", "eles", "elas", "isso", "isto",
    "é", "foi", "ser", "ter", "tem", "pra", "pro", "sua", "seu", "suas", "seus", "essa", "esse", "essas", "esses",
    "muito", "muita", "muitos", "muitas", "também", "então", "porque", "quando", "sem", "antes", "the", "and", "for",
    "with", "from", "this", "that", "you", "your", "are", "was", "were", "have", "has", "had",
}

_GENERIC_MARKERS = (
    "trecho selecionado automaticamente",
    "confira este trecho sobre",
    "short em destaque",
)


def _compact(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _words(value: str) -> list[str]:
    return [word.lower() for word in re.findall(r"[\wÀ-ÿ-]+", _compact(value), flags=re.UNICODE)]


def _meaningful(value: str) -> list[str]:
    return [word for word in _words(value) if len(word) >= 3 and word not in _STOPWORDS]


def _trim(value: str, limit: int) -> str:
    value = _compact(value)
    if len(value) <= limit:
        return value.rstrip(" -|:,.!")
    shortened = value[: limit + 1]
    if " " in shortened:
        shortened = shortened.rsplit(" ", 1)[0]
    return shortened[:limit].rstrip(" -|:,.!")


def _sentences(value: str) -> list[str]:
    compact = _compact(value)
    if not compact:
        return []
    parts = re.split(r"(?<=[.!?])\s+", compact)
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        sentence = _compact(part).strip(" -|,;:")
        if len(sentence) < 12:
            continue
        key = sentence.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(sentence)
    return result


def clip_transcript_text(segments: list[dict], start: float, end: float) -> str:
    parts: list[str] = []
    for segment in segments:
        try:
            segment_start = float(segment.get("start", 0.0))
            segment_end = float(segment.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if segment_end <= start or segment_start >= end:
            continue
        text = _compact(segment.get("text"))
        if text:
            parts.append(text)
    return _compact(" ".join(parts))


def _title_from_content(current_title: str, hook: str, content_text: str, source_title: str) -> str:
    current = _compact(current_title)
    hook_text = _compact(hook)
    sentences = _sentences(content_text)
    source = _compact(source_title)

    candidates = [current, hook_text, sentences[0] if sentences else "", source]
    for candidate in candidates:
        if not candidate:
            continue
        lowered = candidate.casefold()
        if any(marker in lowered for marker in _GENERIC_MARKERS):
            continue
        return _trim(candidate, 88)

    return _trim(source or hook_text or "Short em destaque", 88)


def _description_from_content(title: str, content_text: str, hook: str) -> str:
    sentences = _sentences(content_text)
    selected: list[str] = []
    for sentence in sentences:
        sentence = _trim(sentence, 230)
        if sentence.casefold() == title.casefold():
            continue
        selected.append(sentence)
        if len(selected) == 2:
            break

    if not selected:
        subject = _trim(hook or title, 190)
        selected = [f"Neste Short, você confere {subject}."]

    body = "\n\n".join(selected)
    return f"{body}\n\nAssista ao Short e compartilhe sua opinião nos comentários."[:1200]


def _specific_tag_candidates(content_text: str, hook: str, source_title: str) -> list[str]:
    candidates: list[str] = []
    meaningful = _meaningful(content_text)
    counts = Counter(meaningful)

    # Primeiro entram os conceitos mais recorrentes do próprio corte. Termos
    # funcionais são descartados para abrir espaço às entidades/assuntos reais.
    candidates.extend(word for word, _count in counts.most_common(7))

    raw_words = _words(content_text)[:42]
    # Frases de 2-3 termos capturam melhor intenção de busca e contexto.
    for size in (3, 2):
        for index in range(max(0, len(raw_words) - size + 1)):
            phrase_words = raw_words[index : index + size]
            useful = [word for word in phrase_words if word not in _STOPWORDS and len(word) >= 3]
            if len(useful) < max(1, size - 1):
                continue
            phrase = " ".join(phrase_words)
            if 6 <= len(phrase) <= 60:
                candidates.append(phrase)

    candidates.extend([_trim(hook, 60), _trim(source_title, 60)])
    return [candidate for candidate in candidates if candidate]


def build_qualified_local_seo(
    *,
    source_title: str,
    hook: str,
    content_text: str,
    current_title: str = "",
    current_description: str = "",
    current_tags: list[str] | None = None,
) -> QualifiedSeo:
    """Build unique metadata from the words actually present in one Short.

    This path is deterministic and has no paid API dependency. Existing metadata
    produced by the OpenAI planner is kept when it is already specific; generic
    local-planner text is replaced with clip-specific metadata.
    """

    title = _title_from_content(current_title, hook, content_text, source_title)
    current_description = str(current_description or "").strip()
    lowered_description = current_description.casefold()
    description_is_generic = (
        not current_description
        or any(marker in lowered_description for marker in _GENERIC_MARKERS)
        or len(current_description) < 70
    )
    description = (
        _description_from_content(title, content_text, hook)
        if description_is_generic
        else current_description[:4200].rstrip()
    )

    supplied_tags = [str(tag) for tag in (current_tags or []) if str(tag).strip()]
    specific_candidates = _specific_tag_candidates(content_text, hook, source_title)
    tags = normalize_tags(
        [*supplied_tags, *specific_candidates],
        source_title=source_title,
        hook=hook,
    )

    return QualifiedSeo(title=title, description=description, tags=tags)
