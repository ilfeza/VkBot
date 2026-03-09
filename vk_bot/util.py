from datetime import UTC, datetime


def split_text(text: str, max_length: int = 4096) -> list[str]:
    """Split long text into parts for sending.

    VK API limits messages to 4096 characters.
    Splits by lines and words without breaking words.
    """
    if len(text) <= max_length:
        return [text]

    parts = []
    current = ""

    for line in text.split("\n"):
        if len(current) + len(line) + 1 <= max_length:
            current = f"{current}\n{line}" if current else line
        else:
            if current:
                parts.append(current)

            if len(line) > max_length:
                words = line.split(" ")
                current = ""
                for word in words:
                    if len(current) + len(word) + 1 <= max_length:
                        current = f"{current} {word}" if current else word
                    else:
                        if current:
                            parts.append(current)
                        if len(word) > max_length:
                            parts.extend(
                                word[i : i + max_length]
                                for i in range(0, len(word), max_length)
                            )
                            current = ""
                        else:
                            current = word
            else:
                current = line

    if current:
        parts.append(current)

    return parts


def create_link(text: str, url: str) -> str:
    """Build a VK-formatted link: ``[url|text]``."""
    return f"[{url}|{text}]"


def format_time(timestamp: int) -> str:
    """Format a Unix timestamp to a human-readable string."""
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%d.%m.%Y %H:%M")
