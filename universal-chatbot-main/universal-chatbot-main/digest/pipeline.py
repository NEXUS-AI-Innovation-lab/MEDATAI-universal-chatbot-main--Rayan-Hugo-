"""
Pipeline orchestrator for the digest CLI.
Ties together: scan -> convert -> metadata -> chunk -> upload -> lemmatize -> index.
"""

import os
import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

from pdf_converter import convert_pdfs
from html_converter import convert_htmls
from chunker import chunk_files
from uploader import ensure_collection, upload_chunks
from lemmatizer import lemmatize_points
from indexer import create_index, index_lemmas, add_lemmas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
COLLECTIONS_JSON = SCRIPT_DIR.parent / "server" / "collections.json"
FILESERVER_DIR = SCRIPT_DIR.parent / "storage" / "raw_data"


def _qdrant_name(name: str) -> str:
    return f"{name}_rag_docs"


def _es_name(name: str) -> str:
    return f"{name}_bm25_index"


def _data_dir(name: str) -> Path:
    return DATA_DIR / name


def _md_dir(name: str) -> Path:
    return _data_dir(name) / "markdown"


def _chunks_dir(name: str) -> Path:
    return _data_dir(name) / "chunks"


def _lemmas_dir(name: str) -> Path:
    return _data_dir(name) / "lemmas"


def _manifest_path(name: str) -> Path:
    return _data_dir(name) / "manifest.json"


def _file_content_hash(filepath: str) -> str:
    """SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return f"sha256:{h.hexdigest()}"


def _load_collections() -> dict:
    if COLLECTIONS_JSON.exists():
        with open(COLLECTIONS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_collections(data: dict):
    COLLECTIONS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(COLLECTIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_manifest(name: str) -> dict | None:
    mp = _manifest_path(name)
    if mp.exists():
        with open(mp, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_manifest(manifest: dict, name: str):
    mp = _manifest_path(name)
    mp.parent.mkdir(parents=True, exist_ok=True)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def _copy_to_fileserver(files: dict):
    """
    Copy original source files (PDF/HTML) to the fileserver storage directory.
    Files are named as <hash>.<ext> so the fileserver can serve them via
    GET /download/<hash>.
    """
    FILESERVER_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for file_hash, info in files.items():
        src = Path(info["path"])
        dest = FILESERVER_DIR / f"{file_hash}{src.suffix.lower()}"
        if not dest.exists():
            shutil.copy2(str(src), str(dest))
            copied += 1
    print(f"  Copied {copied} source files to fileserver storage")


def _new_manifest(name: str) -> dict:
    return {
        "collection_name": name,
        "qdrant_collection": _qdrant_name(name),
        "es_index": _es_name(name),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "files": {},
    }


# ---------------------------------------------------------------------------
# Scan input files
# ---------------------------------------------------------------------------

def scan_input_files(input_dir: str, valid_extensions: set[str]) -> dict:
    """
    Scan input_dir for processable files.

    Returns dict of {hash: {path, file_type, original_name}}.
    Hash = filename without extension.

    Validates that every .md file has a matching source file (.pdf or .html).
    Aborts with error if orphan .md files are found.
    """
    input_dir = Path(input_dir)
    files = {}
    md_files = {}  # track .md files separately for validation

    for f in input_dir.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext not in valid_extensions:
            continue

        file_hash = f.stem
        file_type = ext.lstrip(".")

        entry = {
            "path": str(f),
            "file_type": file_type,
            "original_name": f.name,
        }

        if ext == ".md":
            md_files[file_hash] = entry
        else:
            files[file_hash] = entry

    # Validate: every .md file must have a matching source file
    orphan_mds = [
        md_files[h]["original_name"]
        for h in md_files
        if h not in files
    ]
    if orphan_mds:
        raise ValueError(
            f"Orphan .md files found (no matching source .pdf/.html/.htm):\n"
            + "\n".join(f"  - {name}" for name in orphan_mds)
            + "\nEvery .md file must have a corresponding source file with the same basename."
        )

    # Merge .md files in (they override conversion — will be used directly)
    for h, entry in md_files.items():
        files[h]["md_override"] = entry["path"]

    return files


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def _load_metadata(input_dir: str, files: dict) -> dict:
    """
    Load metadata for files. Uses metadata.json if it exists in input_dir,
    otherwise auto-extracts minimal metadata.

    Returns dict keyed by hash -> metadata object.
    """
    input_dir = Path(input_dir)
    metadata_file = input_dir / "metadata.json"
    metadata_map = {}

    external_meta = {}
    if metadata_file.exists():
        with open(metadata_file, "r", encoding="utf-8-sig") as f:
            external_meta = json.load(f)

    for file_hash, info in files.items():
        if file_hash in external_meta:
            meta = external_meta[file_hash].copy()
            # Ensure hash is always set — needed for fileserver citation fallback
            meta.setdefault("hash", file_hash)
            metadata_map[file_hash] = meta
        else:
            # Auto-extract fallback
            metadata_map[file_hash] = {
                "title": info["original_name"],
                "source_url": "",
                "source_type": info["file_type"],
                "hash": file_hash,
                "tags": {},
            }

    return metadata_map


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

def create_collection(name: str, input_dir: str, config, mistral_key: str = None):
    """
    Full pipeline: scan -> convert -> metadata -> chunk -> upload -> lemmatize -> index.
    Creates new Qdrant collection + ES index.
    """
    valid_ext = set(config["processing"]["valid_extensions"].split(","))
    qdrant_url = config["qdrant"]["url"]
    qdrant_col = _qdrant_name(name)
    es_url = config["elasticsearch"]["url"]
    es_idx = _es_name(name)

    # Prepare data dirs
    md_dir = _md_dir(name)
    chunks_dir = _chunks_dir(name)
    lemmas_dir = _lemmas_dir(name)
    for d in [md_dir, chunks_dir, lemmas_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Scan input files
    print(f"\n[1/9] Scanning input files in {input_dir}")
    files = scan_input_files(input_dir, valid_ext)
    print(f"  Found {len(files)} files")

    if not files:
        print("No files to process. Aborting.")
        return

    # 2. Copy source files to fileserver storage
    print(f"\n[2/9] Copying source files to fileserver")
    _copy_to_fileserver(files)

    # 3. Convert PDF/HTML -> markdown (skip .md files)
    print(f"\n[3/9] Converting files to markdown")
    pdf_paths = []
    html_paths = []

    for file_hash, info in files.items():
        if "md_override" in info:
            # .md file exists — copy directly to md_dir
            dest_dir = md_dir / file_hash
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / f"{file_hash}.md"
            if not dest_file.exists():
                shutil.copy2(info["md_override"], dest_file)
            print(f"  [MD] {info['original_name']} (copied directly)")
        elif info["file_type"] == "pdf":
            pdf_paths.append(info["path"])
        elif info["file_type"] in ("html", "htm"):
            html_paths.append(info["path"])

    if pdf_paths:
        if not mistral_key:
            raise ValueError("PDF files found but no --mistral-key provided.")
        print(f"  Converting {len(pdf_paths)} PDFs...")
        convert_pdfs(pdf_paths, str(md_dir), mistral_key)

    if html_paths:
        print(f"  Converting {len(html_paths)} HTML files...")
        convert_htmls(html_paths, str(md_dir))

    # 4. Build metadata
    print(f"\n[4/9] Building metadata")
    metadata_map = _load_metadata(input_dir, files)

    # 5. Chunk markdown files
    print(f"\n[5/9] Chunking markdown files")
    min_tokens = config.getint("chunking", "min_tokens")
    ignore_pattern = config["processing"]["ignore_pattern"]
    chunk_results = chunk_files(
        str(md_dir), str(chunks_dir), metadata_map,
        min_tokens=min_tokens, ignore_pattern=ignore_pattern,
    )

    # 6. Create Qdrant collection + upload
    print(f"\n[6/9] Uploading to Qdrant collection '{qdrant_col}'")
    vector_dim = config.getint("qdrant", "vector_dim")
    ensure_collection(qdrant_url, qdrant_col, vector_dim)
    point_ids = upload_chunks(
        qdrant_url=qdrant_url,
        collection_name=qdrant_col,
        chunks_dir=str(chunks_dir),
        embedding_model=config["qdrant"]["embedding_model"],
        embedding_url=config["qdrant"]["embedding_url"],
        batch_size=config.getint("qdrant", "batch_size"),
        upload_batch_size=config.getint("qdrant", "upload_batch_size"),
        embedding_workers=config.getint("qdrant", "embedding_workers"),
        max_tokens=config.getint("chunking", "max_tokens"),
        tokenizer_encoding=config["chunking"]["tokenizer_encoding"],
    )

    # 7. Lemmatize
    print(f"\n[7/9] Lemmatizing chunks")
    spacy_model = config["spacy"]["model"]
    lemmatize_points(
        qdrant_url=qdrant_url,
        collection_name=qdrant_col,
        output_dir=str(lemmas_dir),
        point_ids=point_ids,
        spacy_model=spacy_model,
    )

    # 8. Create ES index + index all lemmas
    print(f"\n[8/9] Creating ES index '{es_idx}' and indexing lemmas")
    bm25_k1 = config.getfloat("elasticsearch", "bm25_k1")
    bm25_b = config.getfloat("elasticsearch", "bm25_b")
    create_index(es_url, es_idx, bm25_k1, bm25_b)
    index_lemmas(es_url, es_idx, str(lemmas_dir))

    # 9. Update server/collections.json
    print(f"\n[9/9] Updating collections.json")
    collections = _load_collections()
    collections[name] = {"qdrant_collection": qdrant_col, "es_index": es_idx}
    _save_collections(collections)

    # Save manifest
    manifest = _new_manifest(name)
    # Build file entries from chunk results + point_ids
    # We need to map point_ids back to files — for simplicity, store all point_ids
    # grouped by the chunk file they came from
    _build_manifest_from_chunks(manifest, files, chunks_dir, point_ids)
    _save_manifest(manifest, name)

    print(f"\nCollection '{name}' created successfully!")
    print(f"  Qdrant: {qdrant_col}")
    print(f"  ES:     {es_idx}")
    print(f"  Files:  {len(files)}")
    print(f"  Points: {len(point_ids)}")


def _build_manifest_from_chunks(manifest: dict, files: dict, chunks_dir, all_point_ids: list[str]):
    """
    Build manifest file entries by reading chunk files to count chunks,
    and distributing point_ids across files proportionally.

    Since upload_chunks processes files sequentially and returns point_ids in order,
    we can map them back by counting valid chunks per file.
    Only processes files whose hash is present in the `files` dict.
    """
    chunks_dir = Path(chunks_dir)

    # Read chunk files in the same order as upload_chunks would process them
    # Only include files that are in the `files` dict (filters out old files during UPDATE)
    json_files = sorted([
        f for f in chunks_dir.iterdir()
        if f.suffix == ".json" and f.stem in files
    ])

    idx = 0  # pointer into all_point_ids
    for json_file in json_files:
        file_hash = json_file.stem
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            chunks = data["chunks"]
            # Count valid chunks (matching the filter logic in uploader.py)
            valid_count = 0
            for text in chunks:
                if not text.strip():
                    continue
                # We don't re-count tokens here; just count non-empty chunks
                # as an approximation. The exact mapping isn't critical for the manifest.
                valid_count += 1

            # Slice point_ids for this file
            file_point_ids = all_point_ids[idx : idx + valid_count]
            idx += valid_count

            # Build manifest entry
            file_info = files.get(file_hash, {})
            manifest["files"][file_hash] = {
                "original_name": file_info.get("original_name", f"{file_hash}.unknown"),
                "file_type": file_info.get("file_type", "unknown"),
                "content_hash": _file_content_hash(file_info["path"]) if "path" in file_info else "",
                "processed_at": datetime.now().isoformat(),
                "chunks_count": len(file_point_ids),
                "point_ids": file_point_ids,
            }
        except Exception as e:
            print(f"[WARN] Could not build manifest entry for {json_file.name}: {e}")


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

def update_collection(name: str, input_dir: str, config, mistral_key: str = None):
    """
    Add new files to an existing collection.
    Loads manifest, identifies new files, runs pipeline for new files only.
    """
    valid_ext = set(config["processing"]["valid_extensions"].split(","))
    qdrant_url = config["qdrant"]["url"]
    qdrant_col = _qdrant_name(name)
    es_url = config["elasticsearch"]["url"]
    es_idx = _es_name(name)

    # Check collection exists
    collections = _load_collections()
    if name in collections:
        qdrant_col = collections[name]["qdrant_collection"]
        es_idx = collections[name]["es_index"]
    else:
        print(f"Collection '{name}' not found in collections.json.")
        print("Run 'create' first or ensure the collection exists.")
        return

    # Load or rebuild manifest
    manifest = _load_manifest(name)
    if manifest is None:
        print(f"No manifest found for '{name}'. Running rebuild-manifest first...")
        rebuild_manifest(name, config)
        manifest = _load_manifest(name)
        if manifest is None:
            manifest = _new_manifest(name)

    # Scan input files
    print(f"\n[1/6] Scanning input files in {input_dir}")
    all_files = scan_input_files(input_dir, valid_ext)

    # Identify new files (not in manifest by content hash)
    existing_hashes = set(manifest.get("files", {}).keys())
    new_files = {h: info for h, info in all_files.items() if h not in existing_hashes}

    if not new_files:
        print("No new files to process. Everything is up to date.")
        return

    print(f"  Found {len(new_files)} new files (out of {len(all_files)} total)")

    # Prepare dirs
    md_dir = _md_dir(name)
    chunks_dir = _chunks_dir(name)
    lemmas_dir = _lemmas_dir(name)
    for d in [md_dir, chunks_dir, lemmas_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 2. Copy new source files to fileserver storage
    print(f"\n[2/7] Copying new source files to fileserver")
    _copy_to_fileserver(new_files)

    # 3. Convert new files
    print(f"\n[3/7] Converting new files to markdown")
    pdf_paths = []
    html_paths = []

    for file_hash, info in new_files.items():
        if "md_override" in info:
            dest_dir = md_dir / file_hash
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / f"{file_hash}.md"
            if not dest_file.exists():
                shutil.copy2(info["md_override"], dest_file)
            print(f"  [MD] {info['original_name']} (copied directly)")
        elif info["file_type"] == "pdf":
            pdf_paths.append(info["path"])
        elif info["file_type"] in ("html", "htm"):
            html_paths.append(info["path"])

    if pdf_paths:
        if not mistral_key:
            raise ValueError("PDF files found but no --mistral-key provided.")
        print(f"  Converting {len(pdf_paths)} PDFs...")
        convert_pdfs(pdf_paths, str(md_dir), mistral_key)

    if html_paths:
        print(f"  Converting {len(html_paths)} HTML files...")
        convert_htmls(html_paths, str(md_dir))

    # 4. Chunk only new files
    print(f"\n[4/7] Chunking new markdown files")
    metadata_map = _load_metadata(input_dir, new_files)
    min_tokens = config.getint("chunking", "min_tokens")
    ignore_pattern = config["processing"]["ignore_pattern"]

    # Only chunk new files — create a temp chunks dir for new files
    new_chunks_dir = _data_dir(name) / "chunks_new"
    new_chunks_dir.mkdir(parents=True, exist_ok=True)

    chunk_results = chunk_files(
        str(md_dir), str(new_chunks_dir), metadata_map,
        min_tokens=min_tokens, ignore_pattern=ignore_pattern,
        file_hashes=set(new_files.keys()),
    )

    # 5. Upload new chunks to existing Qdrant collection
    print(f"\n[5/7] Uploading new chunks to '{qdrant_col}'")
    point_ids = upload_chunks(
        qdrant_url=qdrant_url,
        collection_name=qdrant_col,
        chunks_dir=str(new_chunks_dir),
        embedding_model=config["qdrant"]["embedding_model"],
        embedding_url=config["qdrant"]["embedding_url"],
        batch_size=config.getint("qdrant", "batch_size"),
        upload_batch_size=config.getint("qdrant", "upload_batch_size"),
        embedding_workers=config.getint("qdrant", "embedding_workers"),
        max_tokens=config.getint("chunking", "max_tokens"),
        tokenizer_encoding=config["chunking"]["tokenizer_encoding"],
    )

    # 6. Lemmatize new chunks
    print(f"\n[6/7] Lemmatizing new chunks")
    spacy_model = config["spacy"]["model"]
    new_lemmas_dir = _data_dir(name) / "lemmas_new"
    new_lemmas_dir.mkdir(parents=True, exist_ok=True)

    lemmatize_points(
        qdrant_url=qdrant_url,
        collection_name=qdrant_col,
        output_dir=str(new_lemmas_dir),
        point_ids=point_ids,
        spacy_model=spacy_model,
    )

    # 7. Add new lemmas to existing ES index
    print(f"\n[7/7] Adding new lemmas to ES index '{es_idx}'")
    add_lemmas(es_url, es_idx, str(new_lemmas_dir), doc_ids=point_ids)

    # Move new chunks/lemmas to main dirs
    for f in new_chunks_dir.iterdir():
        shutil.move(str(f), str(chunks_dir / f.name))
    new_chunks_dir.rmdir()

    for f in new_lemmas_dir.iterdir():
        shutil.move(str(f), str(lemmas_dir / f.name))
    new_lemmas_dir.rmdir()

    # Update manifest
    _build_manifest_from_chunks(manifest, new_files, chunks_dir, point_ids)
    manifest["updated_at"] = datetime.now().isoformat()
    _save_manifest(manifest, name)

    print(f"\nCollection '{name}' updated successfully!")
    print(f"  New files:  {len(new_files)}")
    print(f"  New points: {len(point_ids)}")


# ---------------------------------------------------------------------------
# REBUILD MANIFEST
# ---------------------------------------------------------------------------

def rebuild_manifest(name: str, config):
    """
    Rebuild manifest from an existing Qdrant collection.
    Scrolls the collection, groups points by hash in payload.
    Enables 'update' on legacy collections.
    """
    collections = _load_collections()
    if name in collections:
        qdrant_col = collections[name]["qdrant_collection"]
        es_idx = collections[name]["es_index"]
    else:
        qdrant_col = _qdrant_name(name)
        es_idx = _es_name(name)

    qdrant_url = config["qdrant"]["url"]

    from qdrant_client import QdrantClient
    client = QdrantClient(url=qdrant_url)

    print(f"Scrolling Qdrant collection '{qdrant_col}'...")

    manifest = _new_manifest(name)
    manifest["qdrant_collection"] = qdrant_col
    manifest["es_index"] = es_idx

    file_points = {}  # hash -> list of point_ids

    points, next_page = client.scroll(
        collection_name=qdrant_col,
        limit=2000,
        with_payload=True,
        with_vectors=False,
    )

    def _process_points(points):
        for p in points:
            metadata = p.payload.get("metadata", {})
            # Try to get hash from metadata
            point_hash = metadata.get("hash", "")
            if not point_hash:
                # Fallback: try source_url or other identifiers
                point_hash = metadata.get("source_url", "unknown")

            if point_hash not in file_points:
                file_points[point_hash] = {
                    "point_ids": [],
                    "source_type": metadata.get("source_type", "unknown"),
                    "title": metadata.get("title", ""),
                }
            file_points[point_hash]["point_ids"].append(str(p.id))

    _process_points(points)
    total = len(points)

    while next_page is not None:
        points, next_page = client.scroll(
            collection_name=qdrant_col,
            limit=2000,
            offset=next_page,
            with_payload=True,
            with_vectors=False,
        )
        _process_points(points)
        total += len(points)

    print(f"  Scrolled {total} points, found {len(file_points)} unique sources")

    # Build manifest files entries
    for file_hash, info in file_points.items():
        manifest["files"][file_hash] = {
            "original_name": info.get("title", file_hash),
            "file_type": info.get("source_type", "unknown"),
            "content_hash": "",
            "processed_at": manifest["created_at"],
            "chunks_count": len(info["point_ids"]),
            "point_ids": info["point_ids"],
        }

    _data_dir(name).mkdir(parents=True, exist_ok=True)
    _save_manifest(manifest, name)

    print(f"Manifest saved to {_manifest_path(name)}")
    print(f"  {len(file_points)} files, {total} total points")


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

def list_collections(config):
    """Read and print server/collections.json."""
    collections = _load_collections()

    if not collections:
        print("No collections found.")
        return

    print(f"{'Name':<20} {'Qdrant Collection':<30} {'ES Index':<30}")
    print("-" * 80)
    for name, info in collections.items():
        print(f"{name:<20} {info['qdrant_collection']:<30} {info['es_index']:<30}")
