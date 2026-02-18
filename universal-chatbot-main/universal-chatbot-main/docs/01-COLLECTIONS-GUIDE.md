# Collections Guide

## What is a Collection?

A **collection** is a searchable knowledge base containing documents (PDFs, HTML pages, Markdown files) that have been processed, chunked, and indexed for hybrid search (semantic + keyword).

Each collection consists of:
- **Qdrant Collection**: Vector database storing document embeddings for semantic search
- **Elasticsearch Index**: BM25 index for keyword-based full-text search

Collections are registered in `server/collections.json`:

```json
{
  "btp": {
    "qdrant_collection": "btp_rag_docs_v2",
    "es_index": "btp_bm25_v2_index"
  },
  "medatai": {
    "qdrant_collection": "medatai_rag_docs",
    "es_index": "medatai_bm25_index"
  }
}
```

---

## Prerequisites

Before creating collections, ensure these services are running:

| Service | Default URL | Purpose |
|---------|-------------|---------|
| Qdrant | http://localhost:6333 | Vector database |
| Elasticsearch | http://localhost:9200 | BM25 search |
| Ollama | http://localhost:11434 | Embeddings |
| Fileserver | http://localhost:7700 | File hosting |

You can start them with Docker:
```bash
docker-compose up -d btp-rag-qdrant btp-rag-elasticsearch btp-rag-ollama btp-rag-fileserver
```

---

## Creating a New Collection

### Step 1: Prepare Your Documents

Create a folder with your source documents:

```
my_documents/
├── document1.pdf
├── document2.html
├── document3.md
├── document3.pdf      # Required: source file for .md
└── metadata.json      # Optional: custom metadata
```

**Supported file types:**
- `.pdf` - Converted via Mistral OCR API
- `.html` / `.htm` - Converted via BeautifulSoup
- `.md` - Used directly (must have matching .pdf or .html source)

**Important:** Every `.md` file must have a corresponding `.pdf` or `.html` file with the same name.

### Step 2: Optional Metadata File

Create `metadata.json` in your input folder to provide custom metadata:

```json
{
  "document1.pdf": {
    "title": "Custom Document Title",
    "source_url": "https://example.com/document1",
    "tags": {
      "category": "technical",
      "year": "2024"
    }
  },
  "document2.html": {
    "title": "Another Document",
    "source_url": "https://example.com/document2"
  }
}
```

If not provided, metadata is auto-extracted from the document.

### Step 3: Run the Digest CLI

Navigate to the digest folder and run:

```bash
cd digest/

# Create a new collection
python digest.py create <collection_name> <input_directory> [--mistral-key YOUR_KEY]
```

**Example:**
```bash
python digest.py create my_docs /path/to/my_documents --mistral-key sk-xxxxxxxx
```

**Parameters:**
- `collection_name`: Unique name for your collection (e.g., "my_docs")
- `input_directory`: Path to folder containing your documents
- `--mistral-key`: Required for PDF processing (get from https://console.mistral.ai/)

### Step 4: Verify Creation

The CLI will:
1. Scan and validate input files
2. Copy files to fileserver storage
3. Convert PDFs/HTML to Markdown
4. Chunk documents by headings
5. Upload embeddings to Qdrant
6. Create BM25 index in Elasticsearch
7. Update `server/collections.json`

Check the collection was added:
```bash
python digest.py list
```

Output:
```
Available collections:
  - btp (qdrant: btp_rag_docs_v2, es: btp_bm25_v2_index)
  - my_docs (qdrant: my_docs_rag_docs, es: my_docs_bm25_index)
```

---

## Updating an Existing Collection

To add new documents to an existing collection:

```bash
cd digest/

python digest.py update <collection_name> <input_directory> [--mistral-key YOUR_KEY]
```

**Example:**
```bash
python digest.py update my_docs /path/to/new_documents --mistral-key sk-xxxxxxxx
```

This will:
- Process only new files (not already in manifest)
- Add new chunks to existing Qdrant collection
- Update the Elasticsearch index
- Update the manifest with new files

**Note:** Existing documents are not re-processed. To update a document, you must delete and re-add it manually.

---

## Rebuilding Manifest

If your manifest gets out of sync with Qdrant, rebuild it:

```bash
python digest.py rebuild-manifest <collection_name>
```

This reconstructs the manifest from Qdrant's stored metadata.

---

## Collection Data Structure

After creation, your collection data is stored in:

```
digest/data/<collection_name>/
├── manifest.json           # File registry with point IDs
├── converted/              # Markdown versions of documents
│   ├── <hash>.md
│   └── ...
├── chunks/                 # Chunked JSON files
│   ├── <hash>.json
│   └── ...
└── lemmas/                 # Lemmatized text for BM25
    ├── <point_id>.json
    └── ...
```

### Manifest Structure

```json
{
  "collection_name": "my_docs",
  "qdrant_collection": "my_docs_rag_docs",
  "es_index": "my_docs_bm25_index",
  "created_at": "2025-02-07T10:30:00",
  "updated_at": "2025-02-07T10:30:00",
  "files": {
    "abc123def456": {
      "original_name": "document.pdf",
      "file_type": "pdf",
      "content_hash": "sha256:...",
      "processed_at": "2025-02-07T10:30:00",
      "chunks_count": 15,
      "point_ids": ["uuid-1", "uuid-2", "..."]
    }
  }
}
```

---

## Configuration Options

Edit `digest/config.ini` to customize processing:

```ini
[qdrant]
url = http://localhost:6333
vector_dim = 768
embedding_model = embeddinggemma
embedding_url = http://localhost:11434/api/embeddings

[elasticsearch]
url = http://localhost:9200
bm25_k1 = 1.2
bm25_b = 0.75

[chunking]
min_tokens = 200    # Minimum tokens per chunk
max_tokens = 2000   # Maximum tokens per chunk

[processing]
valid_extensions = .pdf,.html,.htm,.md

[spacy]
model = fr_core_news_sm  # French lemmatization model
```

---

## Deleting a Collection

Currently, deletion must be done manually:

1. **Remove from Qdrant:**
   ```bash
   curl -X DELETE "http://localhost:6333/collections/<qdrant_collection_name>"
   ```

2. **Remove from Elasticsearch:**
   ```bash
   curl -X DELETE "http://localhost:9200/<es_index_name>"
   ```

3. **Remove from collections.json:**
   Edit `server/collections.json` and remove the collection entry.

4. **Remove data folder:**
   ```bash
   rm -rf digest/data/<collection_name>
   ```

---

## Using Collections in the API

Once created, collections appear automatically in all endpoints:

### RAG Endpoint
```bash
curl -X POST http://localhost:8080/rag/api/chat/completions \
  -H "Authorization: Bearer dev-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "my_docs",
    "messages": [{"role": "user", "content": "Your question here"}],
    "stream": true
  }'
```

### QCM Endpoint
```bash
curl -X POST http://localhost:8080/qcm/api/chat/completions \
  -H "Authorization: Bearer dev-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "my_docs",
    "messages": [{"role": "user", "content": "Create a quiz about topic X"}]
  }'
```

### Course Endpoint
```bash
curl -X POST http://localhost:8080/course/api/chat/completions \
  -H "Authorization: Bearer dev-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "my_docs",
    "messages": [{"role": "user", "content": "Create a course about topic Y"}]
  }'
```

---

## Troubleshooting

### "No collections found"
- Check `server/collections.json` exists and has entries
- Verify Qdrant and Elasticsearch are running

### "Embedding model not found"
- Ensure Ollama is running with the embedding model:
  ```bash
  ollama pull embeddinggemma
  ```

### "Mistral API error"
- Verify your API key is valid
- Check your Mistral account has credits

### "spaCy model not found"
- Install the French model:
  ```bash
  python -m spacy download fr_core_news_sm
  ```

### Chunks too small/large
- Adjust `min_tokens` and `max_tokens` in `config.ini`
- Re-process the collection
