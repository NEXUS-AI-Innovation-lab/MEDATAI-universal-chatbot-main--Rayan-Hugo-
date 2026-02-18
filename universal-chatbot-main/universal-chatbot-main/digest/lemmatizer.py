"""
French lemmatization for BM25 indexing.
Refactored from chunker/lemmatization.py.
Supports selective point_ids for UPDATE mode.
"""

import json
import re
from pathlib import Path

import spacy
from tqdm import tqdm
from qdrant_client import QdrantClient


# Lazy-loaded spaCy model
_nlp = None


def _get_nlp(model: str = "fr_core_news_sm"):
    global _nlp
    if _nlp is None:
        _nlp = spacy.load(model)
    return _nlp


def lemmatize_document(text: str, spacy_model: str = "fr_core_news_sm") -> str:
    """Clean markdown formatting and lemmatize French text."""
    # Remove markdown blocks
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"#+\s*", " ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[*_]{1,3}", " ", text)
    text = re.sub(r"^\s*[-*+]\s*", " ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s*", " ", text, flags=re.MULTILINE)
    text = re.sub(r"\|.*\|", " ", text)
    text = re.sub(r"[-*_]{3,}", " ", text)
    text = re.sub(r"[{}\[\]]", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip().lower()

    # Lemmatize
    nlp = _get_nlp(spacy_model)
    doc = nlp(text)
    lemmas = [t.lemma_ for t in doc if not t.is_punct and not t.is_space]

    return " ".join(lemmas)


def lemmatize_points(
    qdrant_url: str,
    collection_name: str,
    output_dir: str,
    point_ids: list[str] = None,
    spacy_model: str = "fr_core_news_sm",
) -> list[str]:
    """
    Fetch chunks from Qdrant, lemmatize, and save as individual JSON files.

    Args:
        qdrant_url: Qdrant server URL.
        collection_name: Qdrant collection to read from.
        output_dir: Directory to write lemma JSON files.
        point_ids: If given, only fetch and lemmatize these points.
                   If None, scroll the entire collection.
        spacy_model: spaCy model name for lemmatization.

    Returns:
        List of saved lemma file paths.
    """
    client = QdrantClient(url=qdrant_url)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_files = []

    def _save_point(p):
        chunk_text = p.payload.get("chunk_text", "")
        lemma = lemmatize_document(chunk_text, spacy_model)

        # Extract hash from metadata
        metadata = p.payload.get("metadata", {})
        point_hash = metadata.get("hash", "")

        obj = {"id": p.id, "lemma": lemma, "hash": point_hash}

        file_path = output_path / f"{p.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

        saved_files.append(str(file_path))

    if point_ids:
        # Fetch specific points in batches
        BATCH = 100
        for i in tqdm(range(0, len(point_ids), BATCH), desc="Lemmatizing"):
            batch_ids = point_ids[i : i + BATCH]
            points = client.retrieve(
                collection_name=collection_name,
                ids=batch_ids,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                _save_point(p)
    else:
        # Scroll entire collection
        print(f"Scrolling entire collection: {collection_name}")
        points, next_page = client.scroll(
            collection_name=collection_name,
            limit=2000,
            with_payload=True,
            with_vectors=False,
        )

        for p in tqdm(points, desc="Lemmatizing"):
            _save_point(p)

        while next_page is not None:
            points, next_page = client.scroll(
                collection_name=collection_name,
                limit=2000,
                offset=next_page,
                with_payload=True,
                with_vectors=False,
            )
            for p in tqdm(points, desc="Lemmatizing"):
                _save_point(p)

    print(f"Lemmatization complete! {len(saved_files)} files saved.")
    return saved_files
