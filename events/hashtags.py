import re


TAG_PATTERN = re.compile(r'^[a-z0-9_]+$')
MAX_TAGS_PER_EVENT = 15
MAX_TAG_LENGTH = 30


def parse_hashtags(raw_text):
    if not raw_text or not raw_text.strip():
        return []

    candidates = re.split(r'[\s,]+', raw_text.strip())
    normalized = []
    seen = set()

    for token in candidates:
        if not token:
            continue
        tag = token.strip().lstrip('#').lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValueError(f"Hashtag '{tag}' is too long. Max {MAX_TAG_LENGTH} characters.")
        if not TAG_PATTERN.fullmatch(tag):
            raise ValueError(
                f"Invalid hashtag '{token}'. Use only letters, numbers, and underscore."
            )
        if tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)

    if len(normalized) > MAX_TAGS_PER_EVENT:
        raise ValueError(f"You can add at most {MAX_TAGS_PER_EVENT} hashtags per event.")

    return normalized
