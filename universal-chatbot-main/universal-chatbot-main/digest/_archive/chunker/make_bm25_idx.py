import os
import json
from elasticsearch import Elasticsearch
from tqdm import tqdm
import configparser

# ==========================================
# CONFIG
# ==========================================
config = configparser.ConfigParser()
config.read('config.ini')

TUMP_DIR = config['paths']['lemmas_dir']
ES_URL = config['elasticsearch']['url']
INDEX_NAME = config['elasticsearch']['index_name']

# Explicit BM25 parameters
BM25_PARAMS = {
    "type": "BM25",
    "k1": config.getfloat('elasticsearch', 'bm25_k1'),
    "b": config.getfloat('elasticsearch', 'bm25_b'),
}


# ==========================================
# CONNECT TO ELASTICSEARCH
# ==========================================

es = Elasticsearch(ES_URL)


# ==========================================
# CREATE INDEX (EXPLICIT BM25 + NO TEXT STORAGE)
# ==========================================

def create_index():
    # Delete old index if needed
    if es.indices.exists(index=INDEX_NAME):
        es.indices.delete(index=INDEX_NAME)

    settings = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "default": {
                        "type": "standard"   # French analyzer if needed
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "doc_id": {
                    "type": "keyword",
                    "store": True    # stored for retrieval
                },
                "text": {
                    "type": "text",
                    "store": False,       # NOT stored
                    "index": True,        # used for BM25
                    "similarity": "my_bm25"
                }
            }
        }
    }

    # Register BM25 similarity explicitly
    settings["settings"]["similarity"] = {
        "my_bm25": BM25_PARAMS
    }

    es.indices.create(index=INDEX_NAME, body=settings)
    print(f"✓ Created index '{INDEX_NAME}' with BM25 params:", BM25_PARAMS)




# ==========================================
# EXAMPLE USAGE
# ==========================================

if __name__ == "__main__":

    # Create index (safe to run again)
    create_index()
    
    # read the tump dir for all the docs
    for f in tqdm(os.listdir(TUMP_DIR)):
        if not f.endswith(".json"):
            continue
        path = os.path.join(TUMP_DIR, f)
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            doc_id = data["id"]
            text = data["lemma"]

             # Index document
            es.index(index=INDEX_NAME, document={
                "doc_id": doc_id,
                "text": text
            })



