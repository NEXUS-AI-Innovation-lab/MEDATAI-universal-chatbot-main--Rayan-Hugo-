import json
from pathlib import Path
from qdrant_client import QdrantClient
import spacy
import re
from tqdm import tqdm
import configparser

# ==========================================
# CONFIG
# ==========================================
config = configparser.ConfigParser()
config.read('config.ini')

# ==========================================
# Load French spaCy once
# ==========================================
_nlp = spacy.load(config['spacy']['model'])



# ==========================================
# Markdown cleaning + Lemmatization
# ==========================================
def lemmatize_document(text: str) -> str:
    """Clean markdown + lemmatize French text."""
    
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



# ==========================================
# Export each chunk into INDIVIDUAL JSON files
# ==========================================
def export_chunks_individual(
    qdrant_url: str,
    collection: str,
    output_dir: str
):
    """
    Load ALL chunks from Qdrant → lemmatize → save each chunk as its own JSON file.
    """

    client = QdrantClient(url=qdrant_url)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"📡 Fetching points from Qdrant collection: {collection}")

    # Initial scroll
    points, next_page = client.scroll(
        collection_name=collection,
        limit=2000,
        with_payload=True,
        with_vectors=False
    )

    total = 0

    # ---------- Helper function ----------
    def save_point(p):
        nonlocal total
        chunk_text = p.payload.get("chunk_text", "")
        lemma = lemmatize_document(chunk_text)

        obj = {
            "id": p.id,
            "lemma": lemma,
            "hash": p.payload.get("hash"),
        }

        file_path = output_path / f"{p.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

        total += 1

    # ---------- Save first batch ----------
    for p in points:
        save_point(p)

    # ---------- Continue scrolling ----------
    while next_page is not None:
        points, next_page = client.scroll(
            collection_name=collection,
            limit=2000,
            offset=next_page,
            with_payload=True,
            with_vectors=False
        )
        for p in tqdm(points):
            save_point(p)

    print(f"\n✅ Export complete! {total} chunks saved individually in:")
    print(f"   {output_path}")

if __name__ == "__main__":
    export_chunks_individual(
        qdrant_url=config['qdrant']['url'],
        collection=config['qdrant']['collection_name'],
        output_dir=config['paths']['lemmas_dir']
    )
    