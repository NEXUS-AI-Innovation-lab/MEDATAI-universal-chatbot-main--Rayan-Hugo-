"""
Elasticsearch BM25 indexer for lemmatized chunks.
Refactored from chunker/make_bm25_idx.py.
Parameterized by index name; supports incremental add for UPDATE mode.
"""

import os
import json
from pathlib import Path

from elasticsearch import Elasticsearch
from tqdm import tqdm


def create_index(es_url: str, index_name: str, bm25_k1: float = 1.2, bm25_b: float = 0.75):
    """
    Create a new Elasticsearch index with explicit BM25 similarity.
    Deletes the old index if it exists.
    """
    es = Elasticsearch(es_url)

    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)

    bm25_params = {"type": "BM25", "k1": bm25_k1, "b": bm25_b}

    settings = {
        "settings": {
            "analysis": {
                "analyzer": {"default": {"type": "standard"}}
            },
            "similarity": {"my_bm25": bm25_params},
        },
        "mappings": {
            "properties": {
                "doc_id": {"type": "keyword", "store": True},
                "text": {
                    "type": "text",
                    "store": False,
                    "index": True,
                    "similarity": "my_bm25",
                },
            }
        },
    }

    es.indices.create(index=index_name, body=settings)
    print(f"Created ES index '{index_name}' with BM25 params: {bm25_params}")


def index_lemmas(es_url: str, index_name: str, lemmas_dir: str):
    """
    Index all lemma JSON files into the Elasticsearch index.
    Used for CREATE mode (indexes everything).
    """
    es = Elasticsearch(es_url)
    lemmas_dir = Path(lemmas_dir)

    files = [f for f in lemmas_dir.iterdir() if f.suffix == ".json"]
    print(f"Indexing {len(files)} lemma files into '{index_name}'")

    for f in tqdm(files, desc="Indexing"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            doc_id = data["id"]
            text = data["lemma"]

            es.index(index=index_name, document={"doc_id": doc_id, "text": text})
        except Exception as e:
            print(f"[ERROR] Failed to index {f.name}: {e}")

    print(f"Indexing complete for '{index_name}'.")


def add_lemmas(es_url: str, index_name: str, lemmas_dir: str, doc_ids: list[str] = None):
    """
    Incrementally add lemma files to an EXISTING Elasticsearch index.
    Used for UPDATE mode — does NOT delete/recreate the index.

    Args:
        es_url: Elasticsearch URL.
        index_name: Target index name.
        lemmas_dir: Directory containing lemma JSON files.
        doc_ids: If given, only index these specific point IDs.
                 If None, indexes all files in lemmas_dir.
    """
    es = Elasticsearch(es_url)
    lemmas_dir = Path(lemmas_dir)

    if doc_ids:
        files = [lemmas_dir / f"{did}.json" for did in doc_ids]
        files = [f for f in files if f.exists()]
    else:
        files = [f for f in lemmas_dir.iterdir() if f.suffix == ".json"]

    print(f"Adding {len(files)} lemma files to '{index_name}'")

    for f in tqdm(files, desc="Adding lemmas"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            doc_id = data["id"]
            text = data["lemma"]

            es.index(index=index_name, document={"doc_id": doc_id, "text": text})
        except Exception as e:
            print(f"[ERROR] Failed to index {f.name}: {e}")

    print(f"Added {len(files)} documents to '{index_name}'.")
