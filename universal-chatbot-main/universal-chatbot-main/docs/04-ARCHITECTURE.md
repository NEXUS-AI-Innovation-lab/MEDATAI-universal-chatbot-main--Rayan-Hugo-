# System Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USERS                                       │
│                         (Web Browser)                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           LIBRECHAT UI                                   │
│                     (http://localhost:3080)                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                      │
│  │ RAG Hybrid  │  │   Course    │  │     QCM     │                      │
│  │  Endpoint   │  │  Generator  │  │  Generator  │                      │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                      │
└─────────┼────────────────┼────────────────┼─────────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        RAG SERVER (FastAPI)                              │
│                     (http://localhost:8080)                              │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                        API LAYER                                  │   │
│  │  /rag/api/*        /course/api/*        /qcm/api/*               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      SERVICE LAYER                                │   │
│  │  rag_service      course_service       qcm_service               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                       RAG ENGINE                                  │   │
│  │  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐  │   │
│  │  │    Context     │    │   LLM Call     │    │   Citation     │  │   │
│  │  │   Retrieval    │───▶│   (Ollama)     │───▶│   Formatting   │  │   │
│  │  └────────────────┘    └────────────────┘    └────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    HYBRID RETRIEVER                               │   │
│  │  ┌─────────────────────┐    ┌─────────────────────┐              │   │
│  │  │   Vector Search     │    │    BM25 Search      │              │   │
│  │  │     (Qdrant)        │    │  (Elasticsearch)    │              │   │
│  │  └─────────┬───────────┘    └──────────┬──────────┘              │   │
│  │            │                           │                          │   │
│  │            └─────────┬─────────────────┘                          │   │
│  │                      ▼                                            │   │
│  │            ┌─────────────────┐                                    │   │
│  │            │  RRF Fusion     │                                    │   │
│  │            │  (Rank Merge)   │                                    │   │
│  │            └─────────────────┘                                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA STORES                                      │
│                                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │   Qdrant   │  │Elasticsearch│  │   Ollama   │  │ Fileserver │        │
│  │  (Vectors) │  │   (BM25)   │  │   (LLM)    │  │  (Files)   │        │
│  │   :6333    │  │   :9200    │  │   :11434   │  │   :7700    │        │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. LibreChat UI

Open-source chat interface that connects to custom endpoints.

**Key Files:**
- `front/.env` - Environment variables
- `front/librechat.yaml` - Endpoint configuration

**Features:**
- Multi-endpoint support (RAG, Course, QCM)
- Conversation history
- Model/collection selection
- Streaming responses

---

### 2. RAG Server (FastAPI)

Main application server handling all API requests.

**Directory Structure:**
```
server/
├── main.py                    # Entry point
├── config_loader.py           # Configuration
├── collections.json           # Collection registry
├── app/
│   ├── main.py               # FastAPI app
│   ├── api/routes/           # Endpoint handlers
│   ├── services/             # Business logic
│   ├── models/schemas.py     # Request/response models
│   └── core/auth.py          # Authentication
├── rag_engine/
│   └── rag.py                # RAG query pipeline
├── retrivers/
│   └── hybrid_retriever.py   # Dual search
├── course_build_agents/      # Course generation
└── qcm_agents/               # Quiz generation
```

---

### 3. Hybrid Retriever

Combines two search methods for better results:

```
Query: "What is the safety procedure?"
           │
           ▼
    ┌──────────────┐
    │   Preprocess │
    │  (Lemmatize) │
    └──────┬───────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌─────────┐
│ Vector  │ │  BM25   │
│ Search  │ │ Search  │
│(Semantic)│ │(Keyword)│
└────┬────┘ └────┬────┘
     │           │
     │  Results  │
     │           │
     └─────┬─────┘
           ▼
    ┌──────────────┐
    │  RRF Fusion  │
    │ (Rank Merge) │
    └──────┬───────┘
           ▼
    Top-K Chunks
```

**Fusion Formula:**
```
Score = 0.5 × (1/(rank_bm25 + 60)) + 0.5 × (1/(rank_vector + 60))
```

---

### 4. RAG Query Flow

```
User Question
      │
      ▼
┌─────────────────┐
│ Hybrid Retrieve │──▶ Top-K chunks with metadata
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Build Prompt    │──▶ <knowledge_base>...</knowledge_base>
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Call LLM       │──▶ Answer with [SOURCE X] citations
│  (Ollama)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Format Citations│──▶ [1](url) [2](url)
└────────┬────────┘
         │
         ▼
Final Response + Sources
```

---

### 5. Course Generation Pipeline

Three-agent architecture:

```
Subject Input
      │
      ▼
┌─────────────────────────────────────┐
│     AGENT 1: Knowledge Retriever    │
│  - Generates search queries         │
│  - Retrieves chunks via RAG         │
│  - Synthesizes knowledge base       │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│     AGENT 2: Knowledge Enhancer     │
│  - Identifies knowledge gaps        │
│  - Retrieves additional context     │
│  - Iterates 3 times                 │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│     AGENT 3: Course Generator       │
│  - Creates chapter structure        │
│  - Writes course content            │
│  - Formats as Markdown              │
└────────────────┬────────────────────┘
                 │
                 ▼
        Course Markdown
```

---

### 6. Document Ingestion Pipeline

```
Input Documents (PDF/HTML/MD)
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│                      DIGEST CLI                               │
│                                                               │
│  Step 1: Scan & Validate                                     │
│     ↓                                                         │
│  Step 2: Copy to Fileserver                                  │
│     ↓                                                         │
│  Step 3: Convert to Markdown (Mistral OCR / BeautifulSoup)   │
│     ↓                                                         │
│  Step 4: Extract Metadata                                    │
│     ↓                                                         │
│  Step 5: Chunk by Headings                                   │
│     ↓                                                         │
│  Step 6: Embed & Upload to Qdrant                            │
│     ↓                                                         │
│  Step 7: Lemmatize for BM25                                  │
│     ↓                                                         │
│  Step 8: Index in Elasticsearch                              │
│     ↓                                                         │
│  Step 9: Update collections.json                             │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
Collection Ready for Queries
```

---

## Data Flow

### Query Flow
```
LibreChat → RAG Server → Hybrid Retriever → Qdrant + ES
                ↓
            LLM (Ollama)
                ↓
         Formatted Response → LibreChat
```

### Ingestion Flow
```
Documents → Digest CLI → Markdown → Chunks → Qdrant + ES
                ↓
            Fileserver (raw files)
```

### File Access Flow
```
User clicks source link → Fileserver → PDF/HTML download
```

---

## Port Mapping

| Service | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------|
| LibreChat | 3080 | 3080 | Web UI |
| RAG Server | 8080 | 8080 | API |
| Qdrant | 6333 | (internal) | Vector DB |
| Elasticsearch | 9200 | (internal) | BM25 |
| Ollama | 11434 | (internal) | LLM |
| Fileserver | 8000 | 7700 | Files |
| MongoDB | 27017 | (internal) | LibreChat data |
| MeiliSearch | 7700 | (internal) | LibreChat search |

---

## Authentication Flow

```
Request with "Authorization: Bearer <token>"
                    │
                    ▼
            ┌───────────────┐
            │  Parse Token  │
            └───────┬───────┘
                    │
                    ▼
            ┌───────────────┐
            │ Lookup in     │
            │ AUTH_TOKENS   │
            └───────┬───────┘
                    │
            ┌───────┴───────┐
            │               │
         Found           Not Found
            │               │
            ▼               ▼
    Return user_info    401 Error
```

**AUTH_TOKENS format:**
```
token1:user_id1:name1,token2:user_id2:name2
```

---

## Configuration Hierarchy

```
Environment Variables (highest priority)
         │
         ▼
    config.ini
         │
         ▼
  Default Values (lowest priority)
```

**Key Configuration Files:**
- `server/config.ini` - Server settings
- `server/collections.json` - Collections
- `digest/config.ini` - Ingestion settings
- `front/.env` - LibreChat settings
- `front/librechat.yaml` - Endpoint config
