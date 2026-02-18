# BTP RAG Document Processing Pipeline

This project processes building and construction (BTP) documents for a Retrieval-Augmented Generation (RAG) system. It includes metadata extraction, markdown chunking, vector embeddings with Qdrant, lemmatization, and BM25 indexing with Elasticsearch.

## Prerequisites

### Required Software

1. **Python 3.8+**
   - Download from [python.org](https://www.python.org/downloads/)

2. **Qdrant Vector Database**
   - Install via Docker:
     ```bash
     docker run -p 6333:6333 qdrant/qdrant
     ```
   - Or download from [qdrant.tech](https://qdrant.tech/documentation/quick-start/)

3. **Ollama (for embeddings)**
   - Download from [ollama.ai](https://ollama.ai/)
   - Install the embedding model:
     ```bash
     ollama pull embeddinggemma
     ```

4. **Elasticsearch**
   - Install via Docker:
     ```bash
     docker run -p 9200:9200 -e "discovery.type=single-node" docker.elastic.co/elasticsearch/elasticsearch:8.11.0
     ```
   - Or download from [elastic.co](https://www.elastic.co/downloads/elasticsearch)

5. **spaCy French Model**
   - Will be installed in setup steps below

## Installation

### 1. Clone or Extract the Project

Navigate to the project directory:
```bash
cd "D:\upec\CHIBANI\chunker (Gold)"
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv
```

Activate the virtual environment:
- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **Linux/Mac:**
  ```bash
  source venv/bin/activate
  ```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Download spaCy French Model

```bash
python -m spacy download fr_core_news_sm
```

## Configuration

### Edit `config.ini`

Before running the scripts, update the paths in `config.ini` to match your environment:

```ini
[paths]
dataset_dir = D:\DATASETS\btp-rag              # Your dataset directory
tump_dir = D:\upec\CHIBANI\btp-rag\tump      # Your temporary/output directory
```

Update other paths as needed relative to your dataset structure.

### Configuration Sections

- **[paths]**: Directory paths for input/output data
- **[metadata_sources]**: Paths to different metadata source types
- **[chunking]**: Token limits and encoding settings
- **[qdrant]**: Vector database connection and settings
- **[elasticsearch]**: Search index settings and BM25 parameters
- **[processing]**: File extensions and processing rules
- **[spacy]**: NLP model configuration

## Usage

The pipeline consists of 5 main scripts that should be run in order:

### 1. Metadata Unification

Process and unify metadata from various sources:

```bash
python metadata_unification.py
```

**Purpose:** Validates resources, expands metadata, and creates unified metadata entries.

### 2. Markdown Chunking

Split markdown documents into semantic chunks:

```bash
python md_hashtag_chunker.py
```

**Purpose:**
- Cleans markdown content
- Chunks based on heading hierarchy
- Respects minimum token thresholds (default: 200 tokens)
- Outputs JSON files with chunks and metadata

### 3. Upload to Qdrant

Generate embeddings and upload to vector database:

```bash
python qdrant_uploader.py
```

**Purpose:**
- Reads chunked documents
- Generates embeddings using Ollama
- Uploads vectors to Qdrant collection
- Filters chunks by token count (max: 2000 tokens)

**Note:** Ensure Qdrant and Ollama are running before executing this script.

### 4. Lemmatization

Extract and lemmatize chunks for BM25 indexing:

```bash
python lemmatization.py
```

**Purpose:**
- Fetches chunks from Qdrant
- Cleans markdown syntax
- Lemmatizes French text using spaCy
- Saves lemmatized text as individual JSON files

### 5. Create BM25 Index

Index lemmatized documents in Elasticsearch:

```bash
python make_bm25_idx.py
```

**Purpose:**
- Creates Elasticsearch index with BM25 similarity
- Configures BM25 parameters (k1=1.2, b=0.75)
- Indexes all lemmatized documents

**Note:** Ensure Elasticsearch is running before executing this script.

## Pipeline Overview

```
Raw Data
    ↓
1. metadata_unification.py → Unified Metadata
    ↓
2. md_hashtag_chunker.py → Chunked Documents (JSON)
    ↓
3. qdrant_uploader.py → Vector Embeddings in Qdrant
    ↓
4. lemmatization.py → Lemmatized Chunks (JSON)
    ↓
5. make_bm25_idx.py → BM25 Index in Elasticsearch
```

## Directory Structure

```
chunker (Gold)/
├── config.ini                  # Configuration file
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── metadata_unification.py     # Step 1
├── md_hashtag_chunker.py      # Step 2
├── qdrant_uploader.py         # Step 3
├── lemmatization.py           # Step 4
└── make_bm25_idx.py           # Step 5
```

## Troubleshooting

### Common Issues

1. **Module not found errors**
   - Ensure virtual environment is activated
   - Run `pip install -r requirements.txt` again

2. **Connection refused to Qdrant/Elasticsearch**
   - Verify services are running
   - Check URLs in `config.ini` match your setup

3. **spaCy model not found**
   - Run `python -m spacy download fr_core_news_sm`

4. **Path errors**
   - Update all paths in `config.ini` to match your system
   - Use absolute paths for reliability

5. **Memory errors during embedding**
   - Reduce `embedding_workers` in config.ini
   - Reduce `batch_size` in config.ini

## Configuration Parameters

### Key Parameters to Adjust

- **min_tokens**: Minimum chunk size (default: 200)
- **max_tokens**: Maximum chunk size (default: 2000)
- **embedding_workers**: Parallel embedding threads (default: 8)
- **batch_size**: Chunks processed per batch (default: 64)
- **bm25_k1**: BM25 term frequency saturation (default: 1.2)
- **bm25_b**: BM25 document length normalization (default: 0.75)

## License

This project is for educational and research purposes.
