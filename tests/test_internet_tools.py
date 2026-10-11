from __future__ import annotations

import pytest

from bot.internet_tools import InternetDownloader, InvalidInternetURL


def test_extract_url_strips_punctuation():
    assert InternetDownloader.extract_url("скачай https://example.com/a.zip).") == "https://example.com/a.zip"


def test_normalize_rejects_non_http():
    with pytest.raises(InvalidInternetURL):
        InternetDownloader._normalize_url("file:///etc/passwd")


def test_normalize_rejects_credentials():
    with pytest.raises(InvalidInternetURL):
        InternetDownloader._normalize_url("https://user:pass@example.com/file")


def test_normalize_accepts_https():
    assert InternetDownloader._normalize_url("https://example.com/file") == "https://example.com/file"
