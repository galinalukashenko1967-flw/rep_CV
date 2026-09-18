"""Extract plain text from an uploaded CV file (.pdf or .docx)."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".doc":
        # Legacy binary Word format has no good pure-Python reader; ask
        # the person to re-save as .docx or .pdf instead of guessing.
        raise ValueError(
            "Старый формат .doc не поддерживается, пересохраните CV как .docx или .pdf"
        )
    raise ValueError(f"Неизвестный формат файла: {suffix}")


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    paragraphs = [p.text for p in document.paragraphs]
    return "\n".join(paragraphs).strip()
