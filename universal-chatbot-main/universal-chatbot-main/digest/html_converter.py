"""
HTML → Markdown converter.
Converted from ocr/html_to_md.ipynb.
Simplified: no image download (images are stripped during chunking).
"""

import os
from pathlib import Path
from bs4 import BeautifulSoup, Comment
from markdownify import markdownify as md
from tqdm import tqdm


def clean_html(html: str) -> str:
    """
    Clean HTML by removing scripts, styles, comments,
    inline CSS, noisy attributes, and empty tags.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts & styles
    for tag in soup(["script", "style"]):
        tag.decompose()

    # Remove comments
    for c in soup.find_all(string=lambda text: isinstance(text, Comment)):
        c.extract()

    # Remove inline styles & noisy attributes
    noisy_attrs = ["class", "id", "style", "onclick", "onload", "width", "height"]
    for tag in soup.find_all():
        for a in noisy_attrs:
            if a in tag.attrs:
                del tag[a]

    # Remove <head> entirely
    if soup.head:
        soup.head.decompose()

    # Remove empty tags except img
    for tag in soup.find_all():
        if tag.name == "img":
            continue
        if not tag.get_text(strip=True) and not tag.contents:
            tag.decompose()

    return str(soup)


def html_to_markdown(html: str) -> str:
    """Convert raw HTML to clean ATX-style Markdown."""
    clean = clean_html(html)
    markdown = md(clean, heading_style="ATX")
    return markdown.strip()


def convert_html(html_path: str, output_dir: str) -> str:
    """
    Convert a single HTML file to markdown.

    Saves output as <output_dir>/<hash>/<hash>.md.
    Returns the path to the generated .md file, or None if skipped.
    """
    html_path = Path(html_path)
    base_name = html_path.stem

    out_dir = os.path.join(output_dir, base_name)
    md_path = os.path.join(out_dir, f"{base_name}.md")

    # Skip if already converted
    if os.path.exists(md_path):
        return md_path

    os.makedirs(out_dir, exist_ok=True)

    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_html = f.read()

    markdown = html_to_markdown(raw_html)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    return md_path


def convert_htmls(html_paths: list[str], output_dir: str) -> list[str]:
    """
    Batch-convert HTML files to markdown.

    Args:
        html_paths: List of paths to HTML files.
        output_dir: Directory to write <hash>/<hash>.md output.

    Returns:
        List of generated .md file paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    results = []
    for html_path in tqdm(html_paths, desc="Converting HTML"):
        try:
            md_path = convert_html(html_path, output_dir)
            if md_path:
                results.append(md_path)
        except Exception as e:
            print(f"[ERROR] Failed to convert {html_path}: {e}")

    return results
