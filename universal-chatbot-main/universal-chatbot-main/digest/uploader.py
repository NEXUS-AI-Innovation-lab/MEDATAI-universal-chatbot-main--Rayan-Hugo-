"""
Qdrant chunk uploader with Ollama embeddings.
Refactored from chunker/qdrant_uploader.py.
Parameterized by collection name; returns point_ids.
"""

import os
import json
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import requests
import tiktoken
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, PointStruct


# Module-level session for connection reuse
_session = requests.Session()

# Lazy tokenizer
_enc = None


def _get_encoder(encoding: str = "o200k_base"):
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding(encoding)
    return _enc


def _count_tokens(text: str, encoding: str = "o200k_base") -> int:
    return len(_get_encoder(encoding).encode(text))


def _embed_single(text: str, model: str, url: str):
    r = _session.post(url, json={"model": model, "prompt": text})
    r.raise_for_status()
    return r.json()["embedding"]


def _embed_batch_parallel(texts: list[str], model: str, url: str, workers: int) -> list:
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda t: _embed_single(t, model, url), texts))
    return results


def ensure_collection(qdrant_url: str, collection_name: str, vector_dim: int):
    """Create a Qdrant collection if it doesn't already exist."""
    client = QdrantClient(url=qdrant_url)
    existing = {c.name for c in client.get_collections().collections}

    if collection_name not in existing:
        print(f"Creating Qdrant collection '{collection_name}'")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_dim, distance="Cosine"),
        )
    else:
        print(f"Qdrant collection '{collection_name}' already exists")


def upload_chunks(
    qdrant_url: str,
    collection_name: str,
    chunks_dir: str,
    embedding_model: str,
    embedding_url: str,
    batch_size: int = 64,
    upload_batch_size: int = 200,
    embedding_workers: int = 8,
    max_tokens: int = 2000,
    tokenizer_encoding: str = "o200k_base",
) -> list[str]:
    """
    Read JSON chunk files, embed with Ollama, upload to Qdrant.

    Args:
        qdrant_url: Qdrant server URL.
        collection_name: Target Qdrant collection.
        chunks_dir: Directory containing JSON chunk files.
        embedding_model: Ollama embedding model name.
        embedding_url: Ollama embedding API URL.
        batch_size: Batch size for embedding requests.
        upload_batch_size: Batch size for Qdrant upserts.
        embedding_workers: Number of parallel embedding workers.
        max_tokens: Skip chunks with >= this many tokens.
        tokenizer_encoding: Tiktoken encoding name.

    Returns:
        List of all created point IDs (UUIDs as strings).
    """
    client = QdrantClient(url=qdrant_url)
    chunks_dir = Path(chunks_dir)

    json_files = [f for f in chunks_dir.iterdir() if f.suffix == ".json"]
    print(f"Found {len(json_files)} JSON documents")

    all_point_ids = []
    upload_batch = []

    for json_file in tqdm(json_files, desc="Uploading chunks"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            metadata = data["metadata"]
            chunks = data["chunks"]

            # Remove internal id field from metadata if present
            if "id" in metadata:
                del metadata["id"]
        except Exception as e:
            print(f"[ERROR] Failed to read {json_file.name}: {e}")
            continue

        for i in range(0, len(chunks), batch_size):
            chunk_batch = chunks[i : i + batch_size]

            # Filter invalid chunks
            valid_chunks = []
            for text in chunk_batch:
                if not text.strip():
                    continue
                if _count_tokens(text, tokenizer_encoding) >= max_tokens:
                    continue
                valid_chunks.append(text)

            if not valid_chunks:
                continue

            try:
                vectors = _embed_batch_parallel(
                    valid_chunks, embedding_model, embedding_url, embedding_workers
                )
            except Exception as e:
                print(f"[ERROR] Embedding failed in {json_file.name}: {e}")
                continue

            for text, vec in zip(valid_chunks, vectors):
                point_id = str(uuid.uuid4())
                point = PointStruct(
                    id=point_id,
                    vector=vec,
                    payload={"chunk_text": text, "metadata": metadata},
                )
                upload_batch.append(point)
                all_point_ids.append(point_id)

                if len(upload_batch) >= upload_batch_size:
                    client.upsert(collection_name=collection_name, points=upload_batch)
                    upload_batch = []

    # Flush remaining
    if upload_batch:
        client.upsert(collection_name=collection_name, points=upload_batch)

    print(f"Upload complete! {len(all_point_ids)} points created.")
    return all_point_ids
