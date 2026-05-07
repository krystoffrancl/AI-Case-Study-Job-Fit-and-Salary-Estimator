import io

import fitz
from docx import Document

from cv_evaluator.models import CVData
from cv_evaluator.utils.logger import logger


def parse_cv(file_bytes: bytes, filename: str) -> CVData:
    if filename.endswith(".pdf"):
        text = _parse_pdf(file_bytes)
        fmt = "PDF"
    elif filename.endswith(".docx"):
        text = _parse_docx(file_bytes)
        fmt = "DOCX"
    else:
        raise ValueError(f"Nepodporovaný formát: {filename}")

    text = text.strip()
    logger.info(f"Parser: {fmt} → {len(text)} znaků, {text.count(chr(10)) + 1} řádků")
    if len(text) < 100:
        logger.warning(f"Parser: extrahovaný text je velmi krátký ({len(text)} znaků), CV možná není textové")
    return CVData(raw_text=text, filename=filename)


def _parse_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    logger.info(f"Parser: PDF má {len(doc)} stránek")
    return "\n".join(str(page.get_text()) for page in doc)


def _parse_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    logger.info(f"Parser: DOCX má {len(paragraphs)} odstavců")
    return "\n".join(paragraphs)
