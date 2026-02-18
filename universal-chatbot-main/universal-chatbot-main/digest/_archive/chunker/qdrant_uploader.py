import os
import json
import uuid
from pathlib import Path
import requests
import tiktoken
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import configparser

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, PointStruct


# ============================================================
# CONFIG
# ============================================================

config = configparser.ConfigParser()
config.read('config.ini')

JSON_INPUT_DIR = Path(config['paths']['chunks_dir'])

QDRANT_URL = config['qdrant']['url']
COLLECTION = config['qdrant']['collection_name']
VECTOR_DIM = config.getint('qdrant', 'vector_dim')


# ============================================================
# EMBEDDINGS
# ============================================================

session = requests.Session()

def _embed_single(text, model=None):
    if model is None:
        model = config['qdrant']['embedding_model']
    url = config['qdrant']['embedding_url']
    r = session.post(url, json={"model": model, "prompt": text})
    r.raise_for_status()
    return r.json()["embedding"]

def embed_batch_parallel(texts, model=None, workers=None):
    if model is None:
        model = config['qdrant']['embedding_model']
    if workers is None:
        workers = config.getint('qdrant', 'embedding_workers')
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda t: _embed_single(t, model), texts))
    return results


# ============================================================
# TOKEN COUNT
# ============================================================

enc = tiktoken.get_encoding(config['chunking']['tokenizer_encoding'])

def count_tokens(text: str) -> int:
    return len(enc.encode(text))


# ============================================================
# QDRANT INIT
# ============================================================

client = QdrantClient(url=QDRANT_URL)
existing = {c.name for c in client.get_collections().collections}

if COLLECTION not in existing:
    print(f"Creating Qdrant collection '{COLLECTION}'")
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance="Cosine")
    )


# ============================================================
# MAIN PIPELINE
# ============================================================

def upload_json_documents():

    upload_batch = []

    json_files = [f for f in JSON_INPUT_DIR.iterdir() if f.suffix == ".json"]

    print(f"Found {len(json_files)} JSON documents\n")

    for json_file in tqdm(json_files, desc="Processing JSON docs"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            metadata = data["metadata"]
            chunks = data["chunks"]
            # delete the id field from metadata if exists
            if "id" in metadata:
                del metadata["id"]
        except Exception as e:
            print(f"[ERROR] Failed to read {json_file.name}: {e}")
            continue

        # Process chunks in batches
        BATCH_SIZE = config.getint('qdrant', 'batch_size')
        MAX_TOKENS = config.getint('chunking', 'max_tokens')
        UPLOAD_BATCH_SIZE = config.getint('qdrant', 'upload_batch_size')

        for i in range(0, len(chunks), BATCH_SIZE):
            chunk_batch = chunks[i:i+BATCH_SIZE]

            valid_chunks = []
            for text in chunk_batch:
                if not text.strip():
                    continue
                if count_tokens(text) >= MAX_TOKENS:
                    continue
                valid_chunks.append(text)

            if not valid_chunks:
                continue

            try:
                vectors = embed_batch_parallel(valid_chunks)
            except Exception as e:
                print(f"[ERROR] Embedding failed in {json_file.name}: {e}")
                continue

            for text, vec in zip(valid_chunks, vectors):
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vec,
                    payload={
                        "chunk_text": text,
                        "metadata": metadata  # keep original structure
                    }
                )
                upload_batch.append(point)

                if len(upload_batch) >= UPLOAD_BATCH_SIZE:
                    client.upsert(collection_name=COLLECTION, points=upload_batch)
                    upload_batch = []

    if upload_batch:
        client.upsert(collection_name=COLLECTION, points=upload_batch)

    print("\n✨ Upload complete!")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    upload_json_documents()
