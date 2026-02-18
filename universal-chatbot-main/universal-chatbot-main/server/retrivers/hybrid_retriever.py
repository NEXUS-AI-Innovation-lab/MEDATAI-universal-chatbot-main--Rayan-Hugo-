import re
import spacy
from elasticsearch import Elasticsearch
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
import requests
from typing import List, Dict
import sys
from pathlib import Path

# ==========================================================
# SYS.PATH MODIFICATION
# ==========================================================
# This project uses a flat directory structure without a formal Python package.
# To enable imports from sibling directories, we add the parent directory to sys.path.
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.settings import settings

# ==========================================================
# CONFIG
# ==========================================================

# --- Elasticsearch ---
# Initialize with error handling for graceful degradation
es = None
try:
    es = Elasticsearch(settings.ELASTICSEARCH_URL)
    # Test connection
    es.info()
except Exception as e:
    print(f"[WARNING] Failed to connect to Elasticsearch at {settings.ELASTICSEARCH_URL}: {e}")
    print("[WARNING] BM25 search will be unavailable. Only vector search will work.")

# --- Qdrant ---
# Initialize with error handling for graceful degradation
qdrant = None
try:
    qdrant = QdrantClient(url=settings.QDRANT_URL)
except Exception as e:
    print(f"[WARNING] Failed to connect to Qdrant at {settings.QDRANT_URL}: {e}")
    print("[WARNING] Vector search will be unavailable. Only BM25 search will work.")

# --- Embeddings (Ollama) ---
session = requests.Session()

# --- Lemmatizer (French) ---
print("Loading spaCy French model...")
_nlp = spacy.load(settings.SPACY_MODEL)

# Hybrid weights
BM25_WEIGHT = settings.BM25_WEIGHT
VECTOR_WEIGHT = settings.VECTOR_WEIGHT

TOP_K = settings.RETRIEVER_TOP_K
FINAL_K = settings.RETRIEVER_FINAL_K


# ==========================================================
# NORMALIZATION + LEMMATIZATION
# ==========================================================

def normalize_and_lemmatize(text: str) -> str:
    """Clean markdown + lowercase + French lemmatization."""
    # --- Remove markdown blocks ---
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
    doc = _nlp(text)
    lemmas = [t.lemma_ for t in doc if not t.is_punct and not t.is_space]

    return " ".join(lemmas)


# ==========================================================
# EMBEDDING (Qdrant)
# ==========================================================

def _embed(text: str):
    resp = session.post(
        f"{settings.OLLAMA_BASE_URL}/api/embeddings",
        json={"model": settings.EMBED_MODEL, "prompt": text}
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


# ==========================================================
# BM25 SEARCH
# ==========================================================

def bm25_search(query: str, es_index: str, top_k=TOP_K):
    """
    Search using BM25 (Elasticsearch).

    Returns empty list if Elasticsearch is unavailable (graceful degradation).
    """
    if es is None:
        return []  # Graceful degradation: return empty results if ES unavailable

    try:
        query_lem = normalize_and_lemmatize(query)

        resp = es.search(
            index=es_index,
            size=top_k,
            query={"match": {"text": query_lem}},
            stored_fields=["doc_id"]
        )

        results = []
        for hit in resp["hits"]["hits"]:
            results.append({
                "id": hit["fields"]["doc_id"][0],
                "score": hit["_score"],
                "method": "bm25"
            })
        return results
    except Exception as e:
        print(f"[WARNING] BM25 search failed: {e}")
        return []  # Graceful degradation on search error


# ==========================================================
# QDRANT SEARCH
# ==========================================================

def vector_search(query: str, qdrant_collection: str, top_k=TOP_K):
    """
    Search using vector similarity (Qdrant).

    Returns empty list if Qdrant is unavailable (graceful degradation).
    """
    if qdrant is None:
        return []  # Graceful degradation: return empty results if Qdrant unavailable

    try:
        vec = _embed(query)

        res = qdrant.query_points(
            collection_name=qdrant_collection,
            query=vec,
            limit=top_k,
            with_payload=True,
            with_vectors=False
        )

        results = []
        for pt in res.points:
            results.append({
                "id": pt.id,
                "score": pt.score,
                "chunk_text": pt.payload.get("chunk_text", ""),
                "hash": pt.payload.get("hash"),
                "metadata": pt.payload.get("metadata"),
                "method": "vector"
            })
        return results
    except Exception as e:
        print(f"[WARNING] Vector search failed: {e}")
        return []  # Graceful degradation on search error


# ==========================================================
# FETCH CHUNK FROM QDRANT
# ==========================================================

def fetch_chunk(point_id: str, qdrant_collection: str):
    """
    Fetch a single chunk from Qdrant by ID.

    Returns None if Qdrant is unavailable or chunk not found (graceful degradation).
    """
    if qdrant is None:
        return None  # Graceful degradation: return None if Qdrant unavailable

    try:
        res = qdrant.retrieve(
            collection_name=qdrant_collection,
            ids=[point_id],
            with_payload=True,
            with_vectors=False
        )
        if not res:
            return None

        pt = res[0]
        return {
            "id": pt.id,
            "chunk_text": pt.payload.get("chunk_text", ""),
            "hash": pt.payload.get("hash"),
            "metadata": pt.payload.get("metadata")
        }
    except Exception as e:
        print(f"[WARNING] Failed to fetch chunk {point_id}: {e}")
        return None


# ==========================================================
# HYBRID RRF FUSION (dynamic top_k)
# ==========================================================
#
# Reciprocal Rank Fusion (RRF) Algorithm
# --------------------------------------
# RRF combines rankings from multiple retrieval methods (BM25 and vector search)
# into a single fused ranking. The formula for each document is:
#
#   RRF_score(doc) = sum( 1 / (k + rank_i) ) for each retrieval method i
#
# Where:
#   - rank_i is the 0-indexed position of the document in method i's results
#   - k is a smoothing constant (we use k=60, the standard from literature)
#
# Why k=60?
# ---------
# The constant k=60 comes from Cormack et al. (2009) "Reciprocal Rank Fusion
# outperforms Condorcet and individual Rank Learning Methods". This value:
#   - Reduces the impact of high rankings (prevents top-1 from dominating)
#   - Ensures documents ranked lower still contribute meaningfully
#   - Has been empirically validated across many IR benchmarks
#
# Final score calculation:
#   fused_score = BM25_WEIGHT * rrf_bm25 + VECTOR_WEIGHT * rrf_vector
#
# ==========================================================

def hybrid_re_rank(bm25_res, vec_res, final_k):
    """
    Combine BM25 + vector results using Reciprocal Rank Fusion (RRF).

    The algorithm:
    1. Sort each result set by their native scores (descending)
    2. Assign RRF scores based on rank: score = 1/(k + rank), where k=60
    3. Combine RRF scores using weighted average (BM25_WEIGHT + VECTOR_WEIGHT)
    4. Return top final_k documents by fused score

    Args:
        bm25_res: List of dicts with 'id' and 'score' from BM25 search
        vec_res: List of dicts with 'id' and 'score' from vector search
        final_k: Number of results to return

    Returns:
        List of (doc_id, fused_score) tuples, sorted by fused_score descending
    """
    # k=60: RRF smoothing constant (Cormack et al., 2009)
    # Higher k = more weight to lower-ranked documents
    RRF_K = 60

    scores = {}  # {doc_id: {"bm25": float, "vec": float}}

    # --- BM25 RRF scoring ---
    # Sort by native BM25 score, then assign RRF score based on rank
    bm25_sorted = sorted(bm25_res, key=lambda x: -x["score"])
    for rank, item in enumerate(bm25_sorted):
        doc_id = item["id"]
        scores.setdefault(doc_id, {"bm25": 0, "vec": 0})
        scores[doc_id]["bm25"] = 1 / (rank + RRF_K)  # RRF formula

    # --- Vector RRF scoring ---
    # Sort by native vector similarity score, then assign RRF score based on rank
    vec_sorted = sorted(vec_res, key=lambda x: -x["score"])
    for rank, item in enumerate(vec_sorted):
        doc_id = item["id"]
        scores.setdefault(doc_id, {"bm25": 0, "vec": 0})
        scores[doc_id]["vec"] = 1 / (rank + RRF_K)  # RRF formula

    # --- Weighted merge ---
    # Combine the two RRF scores using configurable weights
    fused = []
    for doc_id, s in scores.items():
        fused_score = BM25_WEIGHT * s["bm25"] + VECTOR_WEIGHT * s["vec"]
        fused.append((doc_id, fused_score))

    # --- Sort & return final_k ---
    fused_sorted = sorted(fused, key=lambda x: -x[1])[:final_k]
    return fused_sorted



# ==========================================================
# PUBLIC API — THE ONLY FUNCTION THE USER CALLS
# ==========================================================

def retrieve(prompt: str, qdrant_collection: str, es_index: str, top_k: int = 5):
    """
    Full hybrid pipeline:
    - top_k BM25 candidates
    - top_k vector candidates
    - Fuse and return top_k final results
    """
    # 1. BM25
    bm25_results = bm25_search(prompt, es_index=es_index, top_k=top_k)

    # 2. Vector
    vector_results = vector_search(prompt, qdrant_collection=qdrant_collection, top_k=top_k)

    # 3. Fusion
    fused = hybrid_re_rank(bm25_results, vector_results, final_k=top_k)

    # 4. Fetch chunks from Qdrant
    output = []
    for doc_id, fused_score in fused:
        chunk = fetch_chunk(doc_id, qdrant_collection=qdrant_collection)
        if chunk:
            chunk["fused_score"] = fused_score
            output.append(chunk)

    # Sort again by fused score just to be clean
    output = sorted(output, key=lambda x: -x["fused_score"])

    return output
