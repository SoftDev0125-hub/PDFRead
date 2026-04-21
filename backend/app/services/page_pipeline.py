from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

import fitz  # PyMuPDF


PageRoute = Literal["text", "ocr"]


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


def _ocr_image(pix: fitz.Pixmap) -> str:
    # OCR is optional: requires installed Tesseract binary.
    try:
        import pytesseract
        from PIL import Image
    except Exception as e:  # pragma: no cover
        raise RuntimeError("OCR dependencies missing. Install pytesseract + pillow.") from e

    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return pytesseract.image_to_string(img)


def extract_pages_best_effort(pdf_path: str, *, dpi: int = 300) -> list[PageExtraction]:
    doc = fitz.open(pdf_path)
    out: list[PageExtraction] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        text = _clean_text(page.get_text("text") or "")
        if _has_meaningful_text(text):
            out.append(PageExtraction(page_index=i, route="text", text=text))
            continue

        # OCR route
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        ocr_text = _clean_text(_ocr_image(pix))
        out.append(PageExtraction(page_index=i, route="ocr", text=ocr_text))
    return out

