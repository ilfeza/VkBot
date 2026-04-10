from __future__ import annotations

import pytest

from vk_bot import util


@pytest.mark.parametrize(
    ("text", "max_length"),
    [
        ("hello", 10),
        ("12345", 5),
    ],
)
def test_split_text_returns_original_when_within_limit(
    text: str, max_length: int
) -> None:
    assert util.split_text(text, max_length=max_length) == [text]


def test_split_text_splits_by_lines() -> None:
    parts = util.split_text("aa\nbb\ncc", max_length=5)
    assert parts == ["aa\nbb", "cc"]
    assert all(len(part) <= 5 for part in parts)


def test_split_text_splits_long_line_by_words() -> None:
    parts = util.split_text("one two three four", max_length=8)
    assert parts == ["one two", "three", "four"]
    assert all(len(part) <= 8 for part in parts)


def test_split_text_splits_too_long_word() -> None:
    parts = util.split_text("abcdefghijk", max_length=4)
    assert parts == ["abcd", "efgh", "ijk"]
    assert all(len(part) <= 4 for part in parts)


def test_split_text_mixed_short_and_long_lines() -> None:
    text = "short\none two three four"
    parts = util.split_text(text, max_length=8)
    assert parts == ["short", "one two", "three", "four"]
    assert all(len(part) <= 8 for part in parts)


@pytest.mark.parametrize(
    ("text", "url", "expected"),
    [
        ("ВКонтакте", "https://vk.com", "[https://vk.com|ВКонтакте]"),
        ("", "", "[|]"),
    ],
)
def test_create_link(text: str, url: str, expected: str) -> None:
    assert util.create_link(text=text, url=url) == expected


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (0, "01.01.1970 00:00"),
        (60, "01.01.1970 00:01"),
    ],
)
def test_format_time(timestamp: int, expected: str) -> None:
    assert util.format_time(timestamp) == expected
