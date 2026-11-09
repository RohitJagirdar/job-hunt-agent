from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile

import fitz
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from fastapi import UploadFile
from lxml.etree import XMLSyntaxError


MAX_RESUME_BYTES = 5 * 1024 * 1024
MAX_RESUME_TEXT_LENGTH = 50_000
MIN_RESUME_TEXT_LENGTH = 80
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class ResumeExtractionError(ValueError):
    pass


def extract_resume_text(filename: str, content: bytes) -> str:
    suffix = PurePath(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ResumeExtractionError("Upload a PDF, DOCX, TXT, or Markdown resume.")
    if not content:
        raise ResumeExtractionError("The selected resume file is empty.")
    if len(content) > MAX_RESUME_BYTES:
        raise ResumeExtractionError("Resume files must be 5 MB or smaller.")

    if suffix == ".pdf":
        try:
            with fitz.open(stream=content, filetype="pdf") as document:
                text = "\n".join(page.get_text() for page in document)
        except fitz.FileDataError as error:
            raise ResumeExtractionError("The PDF could not be opened. Check that it is a valid PDF.") from error
    elif suffix == ".docx":
        try:
            document = Document(BytesIO(content))
        except (BadZipFile, PackageNotFoundError, XMLSyntaxError) as error:
            raise ResumeExtractionError("The DOCX file could not be opened. Check that it is a valid Word document.") from error
        chunks = [paragraph.text for paragraph in document.paragraphs]
        chunks.extend(
            cell.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
        )
        text = "\n".join(chunks)
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ResumeExtractionError("Text resumes must be encoded as UTF-8.") from error

    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(normalized) < MIN_RESUME_TEXT_LENGTH:
        raise ResumeExtractionError(
            "Could not extract enough text. If this is a scanned PDF, export it with selectable text first."
        )
    return normalized[:MAX_RESUME_TEXT_LENGTH]


def read_resume_upload(upload: UploadFile) -> str:
    content = upload.file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise ResumeExtractionError("Resume files must be 5 MB or smaller.")
    return extract_resume_text(upload.filename or "", content)
