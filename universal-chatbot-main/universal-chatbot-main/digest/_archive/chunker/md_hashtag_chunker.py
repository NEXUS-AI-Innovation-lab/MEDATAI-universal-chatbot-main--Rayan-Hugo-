import os
import re
import json
from pathlib import Path
from tqdm import tqdm
from metadata_unification import expand_metadata
import tiktoken
import configparser


# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

MIN_TOKENS = config.getint('chunking', 'min_tokens')
DATASET_DIR = Path(config['paths']['dataset_dir'])
TUMP_DIR = Path(config['paths']['tump_dir'])
MD_FILES_PATH = Path(config['paths']['md_files_path'])
VALID_EXTENSIONS = set(config['processing']['valid_extensions'].split(','))
RAW_DATA_DIR = Path(config['paths']['raw_data_dir'])
METADATA_PATH = Path(config['paths']['metadata_path'])

RESOURCE_TYPES_TO_PATH = {
    "amaco": Path(config['metadata_sources']['amaco']),
    "dispositif-rexbp": Path(config['metadata_sources']['dispositif_rexbp']),
    "mooc_batiment": Path(config['metadata_sources']['mooc_batiment']),
    "proreno": Path(config['metadata_sources']['proreno']),
    "tpdemain": Path(config['metadata_sources']['tpdemain'])
}
IGNORE = config['processing']['ignore_pattern']


def count_tokens(text: str) -> int:
    # ChatGPT-OSS uses the GPT-4o tokenizer family
    enc = tiktoken.get_encoding(config['chunking']['tokenizer_encoding'])
    tokens = enc.encode(text)
    return len(tokens)


def clean_markdown(md: str) -> str:
    # 1. Remove images entirely: ![alt](link)
    md = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', md)

    # 2. Replace hyperlinks [text](url) → text
    md = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', md)

    # ---- tp.demain specific cleaning ----
    if "tp.demain" in md:

        lines = md.splitlines()

        # 3. Remove everything BEFORE the first line starting with "#"
        #    (including that # line)
        cut_start = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                cut_start = i
                break

        lines = lines[cut_start:]

        # 4. Remove everything AFTER the line containing "Sources :"
        cut_end = len(lines)
        for i, line in enumerate(lines):
            if "Sources :" in line or "tp.demain" in line:
                cut_end = i  # cut including the Sources : line
                break

        lines = lines[:cut_end]

        md = "\n".join(lines).strip()

    return md


def chunk_md(md_text: str) -> list[str]:
    md_text = clean_markdown(md_text)
    lines = md_text.splitlines()
    titles_stack = ["" for _ in range(10)]
    chunks = []
    current_chunk = []
    current_chunk_tokens = 0
    for line in lines:
        if re.match(IGNORE, line):
            continue
        line_stripped = line.strip()
        number_of_hashes = len(line_stripped) - len(line_stripped.lstrip('#'))
        if number_of_hashes > 0:
            for i in range(number_of_hashes-1 , 10):
                titles_stack[i] = ""
            titles_stack[number_of_hashes - 1] = line_stripped
            if current_chunk_tokens >= MIN_TOKENS:
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
    
    if not current_chunk[-1].startswith('#'):
        chunk_text = "\n".join(current_chunk)
        chunks.append(chunk_text)
    
    return chunks


# load all metadatas 
metadatas = []
for meta_type in tqdm(RESOURCE_TYPES_TO_PATH.keys()):
    for f in os.listdir(RESOURCE_TYPES_TO_PATH[meta_type]):
        # load f as json
        with open(os.path.join(RESOURCE_TYPES_TO_PATH[meta_type], f), 'r', encoding='utf-8') as file:
            meta = json.load(file)
            expand = expand_metadata(meta, meta_type, RAW_DATA_DIR)
            for meta in expand:
                if meta["hash"] in os.listdir(MD_FILES_PATH):
                    metadatas.append(meta)

for meta in tqdm(metadatas):
    md_file_path = MD_FILES_PATH / meta["hash"] / f"{meta['hash']}.md"
    with open(md_file_path, 'r', encoding='utf-8') as f:
        md_text = f.read()
    chunks = chunk_md(md_text)
    output = {
        "metadata": meta["metadata"],  # assuming expand_metadata returns a list and we take the first valid entry
        "chunks": chunks
    }
    output_path = Path(config['paths']['chunks_dir']) / f"{meta['hash']}.json"
    with open(output_path, 'w', encoding='utf-8') as out_file:
        json.dump(output, out_file, ensure_ascii=False, indent=4)



            