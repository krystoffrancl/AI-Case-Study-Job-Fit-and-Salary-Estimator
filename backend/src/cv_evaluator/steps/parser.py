import io
import fitz
from docx import Document
from cv_evaluator.models import CVData


def parse_cv(file_bytes: bytes, filename: str) -> CVData:
    if filename.endswith(".pdf"):
        text = _parse_pdf(file_bytes)
    elif filename.endswith(".docx"):
        text = _parse_docx(file_bytes)
    else:
        raise ValueError(f"Nepodporovaný formát: {filename}")

    return CVData(raw_text=text.strip(), filename=filename)


def _parse_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return "\n".join(str(page.get_text()) for page in doc)


def _parse_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())