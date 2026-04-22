from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import fitz  # PyMuPDF


PageRoute = Literal["text", "skipped"]


@dataclass(frozen=True)
class PageExtraction:
    page_index: int
    route: PageRoute
    text: str


def _clean_text(s: str) -> str:
    s = s.replace("\x00", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _has_meaningful_text(text: str) -> bool:
    t = re.sub(r"\s+", "", text or "")
    return len(t) >= 40


def extract_pages_best_effort(pdf_path: str) -> list[PageExtraction]:
    """
    Extract ONLY visible/extractable PDF text.

    Requirement: do not perform analysis on sections where text is not visible.
    Concretely, we do NOT use OCR. Pages without meaningful extracted text are marked as skipped.
    """
    doc = fitz.open(pdf_path)
    out: list[PageExtraction] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        text = _clean_text(page.get_text("text") or "")
        if _has_meaningful_text(text):
            out.append(PageExtraction(page_index=i, route="text", text=text))
            continue
        out.append(PageExtraction(page_index=i, route="skipped", text=""))
    return out

