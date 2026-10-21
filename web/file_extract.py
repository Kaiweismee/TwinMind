"""從上傳檔案擷取文字（txt / pdf / Word docx / PPT pptx）。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx"}
PREVIEW_MAX_CHARS = 4000
EXTRACT_MAX_CHARS = 50000

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _clip(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars] + "…"


def _xml_texts(root: ET.Element, tag_local: str, ns: str) -> list[str]:
    full = f"{{{ns}}}{tag_local}"
    out: list[str] = []
    for el in root.iter(full):
        if el.text and el.text.strip():
            out.append(el.text.strip())
    return out


def _extract_pdf(data: bytes, max_chars: int) -> str:
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t.strip())
            if sum(len(p) for p in parts) >= max_chars:
                break
    return _clip("\n\n".join(parts), max_chars)


def _extract_docx(data: bytes, max_chars: int) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return _clip("\n\n".join(parts), max_chars)
    except ImportError:
        pass

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paras: list[str] = []
    for p in root.iter(f"{{{_W_NS}}}p"):
        bits = [t.text.strip() for t in p.iter(f"{{{_W_NS}}}t") if t.text and t.text.strip()]
        if bits:
            paras.append("".join(bits))
    return _clip("\n".join(paras), max_chars)


def _extract_pptx(data: bytes, max_chars: int) -> str:
    try:
        from pptx import Presentation

        prs = Presentation(io.BytesIO(data))
        parts: list[str] = []
        for i, slide in enumerate(prs.slides, start=1):
            slide_bits: list[str] = []
            for shape in slide.shapes:
                if not hasattr(shape, "text"):
                    continue
                t = (shape.text or "").strip()
                if t:
                    slide_bits.append(t)
            if slide_bits:
                parts.append(f"【投影片 {i}】\n" + "\n".join(slide_bits))
        return _clip("\n\n".join(parts), max_chars)
    except ImportError:
        pass

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        slide_names = sorted(
            n
            for n in zf.namelist()
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        parts: list[str] = []
        for i, name in enumerate(slide_names, start=1):
            root = ET.fromstring(zf.read(name))
            bits = _xml_texts(root, "t", _A_NS)
            if bits:
                parts.append(f"【投影片 {i}】\n" + "\n".join(bits))
    return _clip("\n\n".join(parts), max_chars)


def extract_document_text(
    filename: str,
    data: bytes,
    *,
    max_chars: int = EXTRACT_MAX_CHARS,
) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in TEXT_EXTENSIONS:
        try:
            return _clip(data.decode("utf-8", errors="ignore"), max_chars)
        except OSError:
            return ""
    if ext == ".pdf":
        try:
            return _extract_pdf(data, max_chars)
        except Exception:
            return ""
    if ext == ".docx":
        try:
            return _extract_docx(data, max_chars)
        except Exception:
            return ""
    if ext == ".pptx":
        try:
            return _extract_pptx(data, max_chars)
        except Exception:
            return ""
    return ""


def preview_text(filename: str, data: bytes) -> str:
    return extract_document_text(filename, data, max_chars=PREVIEW_MAX_CHARS)
