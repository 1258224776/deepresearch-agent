"""
File / artifact adapter layer.

Keeps top-level app/agent entry points off the legacy tools.py module while
preserving the existing storage and upload behavior.
"""

from __future__ import annotations

from tools import parse_uploaded_file, save_report, save_scraped


def parse_uploaded_document(file_bytes: bytes, filename: str) -> str:
    return parse_uploaded_file(file_bytes, filename)


def save_markdown_report(question: str, reply: str) -> str:
    return save_report(question, reply)


def save_scraped_page(url: str, content: str, extracted: str = "") -> str:
    return save_scraped(url, content, extracted)
