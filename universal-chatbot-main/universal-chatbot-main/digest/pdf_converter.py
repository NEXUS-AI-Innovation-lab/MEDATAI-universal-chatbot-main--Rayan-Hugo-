"""
PDF → Markdown converter using Mistral OCR API.
Converted from ocr/mistral_ocr.ipynb.
"""

import os
from pathlib import Path
from tqdm import tqdm
from mistralai import Mistral
import datauri


def _save_image(image, output_dir: str):
    """Decode base64 image from Mistral OCR response and save to disk."""
    parsed = datauri.parse(image.image_base64)
    image_path = os.path.join(output_dir, image.id)
    with open(image_path, "wb") as f:
        f.write(parsed.data)


def convert_pdf(pdf_path: str, output_dir: str, client: Mistral) -> str:
    """
    Convert a single PDF to markdown using Mistral OCR.

    Returns the path to the generated .md file, or None if skipped.
    Deletes the uploaded file from Mistral cloud after processing.
    """
    pdf_path = Path(pdf_path)
    base_name = pdf_path.stem.strip()
    pdf_output_dir = os.path.join(output_dir, base_name)

    # Skip if already converted
    md_path = os.path.join(pdf_output_dir, f"{base_name}.md")
    if os.path.exists(md_path):
        return md_path

    os.makedirs(pdf_output_dir, exist_ok=True)

    # Upload PDF to Mistral
    uploaded = client.files.upload(
        file={"file_name": pdf_path.name, "content": open(pdf_path, "rb")},
        purpose="ocr",
    )

    try:
        signed_url = client.files.get_signed_url(file_id=uploaded.id)

        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "document_url", "document_url": signed_url.url},
            include_image_base64=True,
        )

        # Save markdown
        with open(md_path, "w", encoding="utf-8") as md_file:
            for idx, page in enumerate(ocr_response.pages):
                md_file.write(page.markdown)
                md_file.write(f"\n\n<!-- Page {idx + 1} End -->\n\n")

                # Save images
                for image in page.images:
                    _save_image(image, pdf_output_dir)

    finally:
        client.files.delete(file_id=uploaded.id)

    return md_path


def convert_pdfs(pdf_paths: list[str], output_dir: str, api_key: str) -> list[str]:
    """
    Batch-convert PDFs to markdown.

    Args:
        pdf_paths: List of paths to PDF files.
        output_dir: Directory to write <hash>/<hash>.md output.
        api_key: Mistral API key.

    Returns:
        List of generated .md file paths.
    """
    client = Mistral(api_key=api_key)
    os.makedirs(output_dir, exist_ok=True)

    results = []
    for pdf_path in tqdm(pdf_paths, desc="Converting PDFs"):
        try:
            md_path = convert_pdf(pdf_path, output_dir, client)
            if md_path:
                results.append(md_path)
        except Exception as e:
            print(f"[ERROR] Failed to convert {pdf_path}: {e}")

    return results
