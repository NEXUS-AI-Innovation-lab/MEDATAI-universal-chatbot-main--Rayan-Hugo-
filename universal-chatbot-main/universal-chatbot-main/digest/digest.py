"""
Digest CLI — Create & Update RAG Collections.

Usage:
    python digest.py create <name> <input_dir> [--mistral-key KEY]
    python digest.py update <name> <input_dir> [--mistral-key KEY]
    python digest.py rebuild-manifest <name>
    python digest.py list
"""

import argparse
import configparser
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Digest CLI — Create & Update RAG Collections (Qdrant + Elasticsearch)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- create ---
    p_create = subparsers.add_parser("create", help="Create a new collection from PDF/HTML/MD files")
    p_create.add_argument("name", help="Collection name (e.g. 'finance')")
    p_create.add_argument("input_dir", help="Directory containing input files")
    p_create.add_argument("--mistral-key", help="Mistral API key (required if input contains PDFs)")

    # --- update ---
    p_update = subparsers.add_parser("update", help="Add new files to an existing collection")
    p_update.add_argument("name", help="Collection name")
    p_update.add_argument("input_dir", help="Directory containing input files")
    p_update.add_argument("--mistral-key", help="Mistral API key (required if input contains PDFs)")

    # --- rebuild-manifest ---
    p_rebuild = subparsers.add_parser(
        "rebuild-manifest",
        help="Rebuild manifest from existing Qdrant collection (for legacy collections)",
    )
    p_rebuild.add_argument("name", help="Collection name")

    # --- list ---
    subparsers.add_parser("list", help="List all registered collections")

    args = parser.parse_args()

    # Load config relative to this script
    script_dir = Path(__file__).parent.resolve()
    config = configparser.ConfigParser()
    config_path = script_dir / "config.ini"
    if not config_path.exists():
        print(f"Error: config.ini not found at {config_path}")
        sys.exit(1)
    config.read(str(config_path))

    # Import pipeline here (after config is loaded) to allow the script
    # to be invoked from any working directory.
    sys.path.insert(0, str(script_dir))
    from pipeline import create_collection, update_collection, rebuild_manifest, list_collections

    if args.command == "create":
        input_dir = Path(args.input_dir)
        if not input_dir.is_dir():
            print(f"Error: '{args.input_dir}' is not a directory")
            sys.exit(1)
        create_collection(args.name, str(input_dir), config, mistral_key=args.mistral_key)

    elif args.command == "update":
        input_dir = Path(args.input_dir)
        if not input_dir.is_dir():
            print(f"Error: '{args.input_dir}' is not a directory")
            sys.exit(1)
        update_collection(args.name, str(input_dir), config, mistral_key=args.mistral_key)

    elif args.command == "rebuild-manifest":
        rebuild_manifest(args.name, config)

    elif args.command == "list":
        list_collections(config)


if __name__ == "__main__":
    main()
