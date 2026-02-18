"""
Markdown heading-based chunker.
Refactored from chunker/md_hashtag_chunker.py.
No BTP-specific metadata loading — metadata is passed in as a parameter.
"""

import os
import re
import json
from pathlib import Path
from tqdm import tqdm
import tiktoken


# Module-level tokenizer (lazy-initialized)
_enc = None


def _get_encoder(encoding: str = "o200k_base"):
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding(encoding)
    return _enc


def count_tokens(text: str, encoding: str = "o200k_base") -> int:
    return len(_get_encoder(encoding).encode(text))


def clean_markdown(md: str) -> str:
    """Remove images, convert hyperlinks to text, tp.demain-specific cleaning."""
    # Remove images: ![alt](link)
    md = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', md)

    # Replace hyperlinks [text](url) -> text
    md = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', md)

    # tp.demain specific cleaning
    if "tp.demain" in md:
        lines = md.splitlines()

        # Remove everything BEFORE the first line starting with "#"
        cut_start = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                cut_start = i
                break
        lines = lines[cut_start:]

        # Remove everything AFTER "Sources :" or "tp.demain"
        cut_end = len(lines)
        for i, line in enumerate(lines):
            if "Sources :" in line or "tp.demain" in line:
                cut_end = i
                break
        lines = lines[:cut_end]

        md = "\n".join(lines).strip()

    return md


def chunk_md(md_text: str, min_tokens: int = 200, ignore_pattern: str = None) -> list[str]:
    """
    Split markdown text into chunks based on heading hierarchy.

    Args:
        md_text: Raw markdown text.
        min_tokens: Minimum tokens before a heading triggers a new chunk.
        ignore_pattern: Regex pattern for lines to skip (e.g. page markers).

    Returns:
        List of chunk strings.
    """
    md_text = clean_markdown(md_text)
    lines = md_text.splitlines()
    titles_stack = ["" for _ in range(10)]
    chunks = []
    current_chunk = []
    current_chunk_tokens = 0

    for line in lines:
        if ignore_pattern and re.match(ignore_pattern, line):
            continue

        line_stripped = line.strip()
        number_of_hashes = len(line_stripped) - len(line_stripped.lstrip('#'))

        if number_of_hashes > 0:
            for i in range(number_of_hashes - 1, 10):
                titles_stack[i] = ""
            titles_stack[number_of_hashes - 1] = line_stripped

            if current_chunk_tokens >= min_tokens:
                chunk_text = "\n".join(current_chunk)
                chunks.append(chunk_text)
                current_chunk = [t for t in titles_stack if t]
                current_chunk_tokens = count_tokens("\n".join(current_chunk))
            else:
                current_chunk.append(line_stripped)
                current_chunk_tokens += count_tokens(line_stripped)
        else:
            current_chunk.append(line_stripped)
            current_chunk_tokens += count_tokens(line_stripped)

    # Flush last chunk if it has non-heading content
    if current_chunk and not current_chunk[-1].startswith('#'):
        chunk_text = "\n".join(current_chunk)
        chunks.append(chunk_text)

    return chunks


def chunk_files(
    md_dir: str,
    chunks_dir: str,
    metadata_map: dict,
    min_tokens: int = 200,
    ignore_pattern: str = None,
    file_hashes: set[str] = None,
) -> dict[str, str]:
    """
    Batch-chunk markdown files in md_dir.

    Args:
        md_dir: Directory containing <hash>/<hash>.md files.
        chunks_dir: Output directory for JSON chunk files.
        metadata_map: Dict keyed by hash -> metadata object.
        min_tokens: Minimum tokens per chunk.
        ignore_pattern: Regex pattern for lines to skip.
        file_hashes: If given, only process these file hashes.
                     If None, process all files in md_dir.

    Returns:
        Dict of {hash: output_json_path} for successfully chunked files.
    """
    md_dir = Path(md_dir)
    chunks_dir = Path(chunks_dir)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Find markdown files: <hash>/<hash>.md
    md_files = []
    for subdir in md_dir.iterdir():
        if subdir.is_dir():
            if file_hashes is not None and subdir.name not in file_hashes:
                continue
            md_file = subdir / f"{subdir.name}.md"
            if md_file.exists():
                md_files.append((subdir.name, md_file))

    for file_hash, md_file in tqdm(md_files, desc="Chunking"):
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                md_text = f.read()

            chunks = chunk_md(md_text, min_tokens=min_tokens, ignore_pattern=ignore_pattern)

            # Get metadata for this file (or empty dict)
            metadata = metadata_map.get(file_hash, {})

            output = {"metadata": metadata, "chunks": chunks}

            output_path = chunks_dir / f"{file_hash}.json"
            with open(output_path, "w", encoding="utf-8") as out_file:
                json.dump(output, out_file, ensure_ascii=False, indent=4)

            results[file_hash] = str(output_path)

        except Exception as e:
            print(f"[ERROR] Failed to chunk {md_file}: {e}")

    return results
