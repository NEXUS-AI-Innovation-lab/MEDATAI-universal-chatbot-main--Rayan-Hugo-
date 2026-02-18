# Configuration Reference

Complete reference for all configuration options.

---

## Server Configuration

### File: `server/config.ini`

```ini
[server]
host = 0.0.0.0
port = 8080

[rag]
# LLM model for RAG responses
model = gpt-oss:20b
# Default number of chunks to retrieve
default_top_k = 30
# LLM temperature (0.0 - 1.0)
temperature = 0.7
# Chunk size for streaming (characters)
chunk_size = 5
# Delay between chunks (seconds)
chunk_delay = 0.01

[hybrid_retriever]
# Embedding model name (must be in Ollama)
embed_model = embeddinggemma
# Weight for BM25 results (0.0 - 1.0)
bm25_weight = 0.5
# Weight for vector results (0.0 - 1.0)
vector_weight = 0.5
# Initial retrieval count from each source
top_k = 8
# Final number of chunks after fusion
final_k = 5

[course_generation]
# Chunks per query for knowledge retrieval
retriever_top_k = 5
# Number of enhancement iterations
enhancer_iterations = 3
# Chunks per gap-filling query
enhancer_top_k = 5

[qcm_generation]
# Chunks for question generation context
retriever_top_k = 15
# Chunks per answer generation query
answer_top_k = 5
```

---

### Environment Variables (Server)

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVER_HOST` | Server bind address | `0.0.0.0` |
| `SERVER_PORT` | Server port | `8080` |
| `AUTH_TOKENS` | Authentication tokens | Required |
| `ELASTICSEARCH_URL` | Elasticsearch URL | `http://localhost:9200` |
| `QDRANT_URL` | Qdrant URL | `http://localhost:6333` |
| `OLLAMA_BASE_URL` | Ollama URL | `http://localhost:11434` |
| `OLLAMA_API_KEY` | Ollama cloud API key | None (uses local) |
| `FILESERVER_BASE` | Internal fileserver URL | `http://localhost:7700` |
| `FILESERVER_PUBLIC_URL` | Public fileserver URL | Same as FILESERVER_BASE |

**AUTH_TOKENS Format:**
```
token1:user_id1:name1,token2:user_id2:name2
```

Example:
```bash
AUTH_TOKENS=dev-token-123:user_1:Developer,prod-token-456:user_2:Admin
```

---

## Digest Configuration

### File: `digest/config.ini`

```ini
[qdrant]
# Qdrant server URL
url = http://localhost:6333
# Embedding vector dimension
vector_dim = 768
# Ollama embedding model
embedding_model = embeddinggemma
# Ollama API URL for embeddings
embedding_url = http://localhost:11434/api/embeddings

[elasticsearch]
# Elasticsearch URL
url = http://localhost:9200
# BM25 k1 parameter (term frequency saturation)
bm25_k1 = 1.2
# BM25 b parameter (document length normalization)
bm25_b = 0.75

[chunking]
# Minimum tokens per chunk
min_tokens = 200
# Maximum tokens per chunk (chunks larger than this are filtered)
max_tokens = 2000

[processing]
# Allowed file extensions
valid_extensions = .pdf,.html,.htm,.md
# Pattern to ignore in content
ignore_pattern = <!-- Page\s+\d+\s+End -->

[spacy]
# spaCy model for French lemmatization
model = fr_core_news_sm
```

---

## LibreChat Configuration

### File: `front/.env`

```bash
# =================================================================
# CORE
# =================================================================
HOST=0.0.0.0
PORT=3080

# =================================================================
# DATABASE
# =================================================================
MONGO_URI=mongodb://mongodb:27017/LibreChat

# =================================================================
# SEARCH
# =================================================================
MEILI_HOST=http://meilisearch:7700
MEILI_NO_ANALYTICS=true

# =================================================================
# SECURITY (Change in production!)
# =================================================================
JWT_SECRET=<64-byte-base64>
JWT_REFRESH_SECRET=<64-byte-base64>
CREDS_KEY=<32-byte-hex>
CREDS_IV=<16-byte-hex>

# =================================================================
# SESSION
# =================================================================
SESSION_EXPIRY=900000
REFRESH_TOKEN_EXPIRY=604800000

# =================================================================
# CUSTOM API
# =================================================================
CUSTOM_API_KEY=dev-token-123
DEFAULT_COLLECTION=btp

# =================================================================
# APP
# =================================================================
APP_TITLE=My RAG System
ALLOW_REGISTRATION=true
ALLOW_SOCIAL_LOGIN=false
```

---

### File: `front/librechat.yaml`

```yaml
version: 1.1.7
cache: true

endpoints:
  custom:
    - name: "Endpoint Name"
      apiKey: "${CUSTOM_API_KEY}"           # From .env
      baseURL: "http://server:8080/path/api"
      models:
        default:
          - "${DEFAULT_COLLECTION}"
        fetch: true                          # Fetch from /api/models
      titleConvo: true                       # Auto-generate titles
      titleModel: "${DEFAULT_COLLECTION}"    # Model for titles
      summarize: false                       # Summarize conversations
      forcePrompt: false                     # Force system prompt
      modelDisplayLabel: "Display Name"      # Shown in UI
      iconURL: "https://..."                 # Custom icon
      type: "openai"                         # API format
      dropParams: ["user"]                   # Params to exclude
      addParams:                             # Params to add
        stream: false
      context: 8000                          # Context window
      max_tokens: 4096                       # Max response tokens

interface:
  modelSelect: true        # Show model dropdown
  parameters: false        # Show param controls
  sidePanel: false
  presets: false
  prompts: false
  bookmarks: true
  multiConvo: false
  agents: false
  customWelcome: "Welcome!"
  runCode: false
  webSearch: false
  fileSearch: false
  fileCitations: false

fileConfig:
  endpoints:
    "Endpoint Name":
      disabled: true       # Disable file uploads
```

---

## Collections Registry

### File: `server/collections.json`

```json
{
  "collection_name": {
    "qdrant_collection": "qdrant_collection_name",
    "es_index": "elasticsearch_index_name"
  }
}
```

Example:
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

## Docker Compose Variables

### Production (`docker-compose.yml`)

```yaml
services:
  universal-rag-server:
    environment:
      - AUTH_TOKENS=token:user_id:name
      - ELASTICSEARCH_URL=http://elasticsearch:9200
      - QDRANT_URL=http://qdrant:6333
      - OLLAMA_BASE_URL=http://ollama:11434
      - FILESERVER_BASE=http://fileserver:8000
      - FILESERVER_PUBLIC_URL=http://localhost:7700
```

### Development (`docker-compose-dev.yml`)

Additional settings for development:
```yaml
services:
  universal-rag-server:
    volumes:
      - ./server:/app        # Live code reload
    environment:
      - DEBUG=true
```

---

## Tuning Guide

### Retrieval Quality

| Parameter | Effect | Recommendation |
|-----------|--------|----------------|
| `hybrid_retriever.top_k` | Initial results count | 8-15 |
| `hybrid_retriever.final_k` | Final results count | 3-5 |
| `hybrid_retriever.bm25_weight` | Keyword importance | 0.3-0.5 |
| `hybrid_retriever.vector_weight` | Semantic importance | 0.5-0.7 |

**For technical documents:** Higher BM25 weight (0.5)
**For general content:** Higher vector weight (0.7)

### Chunking Quality

| Parameter | Effect | Recommendation |
|-----------|--------|----------------|
| `chunking.min_tokens` | Minimum chunk size | 150-300 |
| `chunking.max_tokens` | Maximum chunk size | 1500-2500 |

**For dense technical docs:** Smaller chunks (200-1000)
**For narrative content:** Larger chunks (300-2000)

### LLM Response

| Parameter | Effect | Recommendation |
|-----------|--------|----------------|
| `rag.temperature` | Creativity | 0.3-0.7 |
| `rag.default_top_k` | Context size | 20-50 |

**For factual answers:** Lower temperature (0.3)
**For creative tasks:** Higher temperature (0.7)

---

## Generating Secrets

```bash
# JWT secrets (64 bytes, base64)
openssl rand -base64 64

# Credentials key (32 bytes, hex)
openssl rand -hex 32

# Credentials IV (16 bytes, hex)
openssl rand -hex 16

# API token (32 bytes, hex)
openssl rand -hex 32
```
