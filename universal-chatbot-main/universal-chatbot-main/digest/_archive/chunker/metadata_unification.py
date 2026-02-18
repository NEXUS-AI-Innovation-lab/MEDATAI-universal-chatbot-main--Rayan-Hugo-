import os
from pathlib import Path
import uuid
import json
from tqdm import tqdm
import configparser


# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

DATASET_DIR = Path(config['paths']['dataset_dir'])
TUMP_DIR = Path(config['paths']['tump_dir'])
VALID_EXTENSIONS = set(config['processing']['valid_extensions'].split(','))
RAW_DATA_DIR = Path(config['paths']['raw_data_dir'])
METADATA_PATH = Path(config['paths']['metadata_path'])
UNIFIED_METADATA_PATH = Path(config['paths']['unified_metadata_path'])


def save_json(data: list, output_path: Path):
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')


def is_valid_resource(hash_value: str, raw_data_dir: Path) -> bool:
    if not hash_value:
        return False
    # Check for any file matching hash.*
    candidates = list(raw_data_dir.glob(f"{hash_value}.*"))
    return any(c.suffix.lower() in VALID_EXTENSIONS for c in candidates)


def expand_metadata(meta: dict, source_type: str, raw_data_dir: Path = RAW_DATA_DIR) -> list:
    """
    Build resource entries ONLY if the hash corresponds to a valid file in raw_data_dir.
    """

    # All possible hash/url pairs
    possible_resources = [
        ("html_hash", meta.get("url")),
        ("file_hash", meta.get("file_download_url")),
        ("pdf_hash", meta.get("pdf_download_url")),
        ("external_hash", meta.get("external_url")),
        ("video_hash", meta.get("video_url")),
    ]

    resources = []
    for hash_key, url in possible_resources:
        hash_value = meta.get(hash_key)
        if hash_value and is_valid_resource(hash_value, raw_data_dir):
            resources.append((hash_value, url))

    # If nothing valid, fallback on html hash if present but file missing
    # (optional: can be removed if strict)
    if not resources and meta.get("html_hash") and meta.get("url"):
        resources.append((meta["html_hash"], meta["url"]))

    # → Separated tags
    tags = {
        "topics": meta.get("topics", []),
        "themes": meta.get("themes", []),
        "keywords": meta.get("keywords", []),
        "work_phases": meta.get("work_phases", []),
        "trade_categories": meta.get("trade_categories", []),
        "project_types": meta.get("project_types", []),
        "raw_tags": meta.get("tags", []),
    }

    description = (
        meta.get("description")
        or meta.get("introduction")
        or meta.get("summary")
    )

    core_keys = {
        "html_hash", "file_hash", "pdf_hash",
        "external_hash", "video_hash",
        "url", "file_download_url", "pdf_download_url",
        "external_url", "video_url",
        "title", "topics", "themes", "keywords", "tags",
        "work_phases", "trade_categories", "project_types",
        "description", "introduction", "summary", "document_type"
    }

    extra = {k: v for k, v in meta.items() if k not in core_keys}

    result = []

    for hash_value, url in resources:

        metadata_obj = {
            "id": str(uuid.uuid4()),
            "source_type": source_type,
            "source_url": url,
            "title": meta.get("title", ""),
            "document_type": meta.get("document_type"),
            "tags": tags,
            "description": description,
            "extra": extra
        }

        result.append({
            "hash": hash_value,
            "metadata": metadata_obj
        })

    return result





            
    