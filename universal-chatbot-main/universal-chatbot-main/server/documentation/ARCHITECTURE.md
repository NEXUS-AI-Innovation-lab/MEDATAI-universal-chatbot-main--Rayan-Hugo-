# Server Architecture

## Overview

The server has been refactored into a modular architecture following best practices for FastAPI applications.

## Directory Structure

```
server/
├── main.py                         # Entry point with uvicorn
├── config.ini                      # Application settings (non-sensitive)
├── .env                            # Environment variables (secrets)
├── collections.json                # Collection registry
├── config_loader.py                # DEPRECATED - redirects to settings
│
├── app/                            # Main application package
│   ├── main.py                     # FastAPI app factory
│   │
│   ├── api/                        # API layer
│   │   └── routes/                 # Route modules
│   │       ├── rag.py             # RAG endpoints
│   │       ├── qcm.py             # QCM endpoints
│   │       └── course.py          # Course endpoints
│   │
│   ├── core/                       # Core components
│   │   ├── auth.py                # Authentication & authorization
│   │   └── settings.py            # Centralized Pydantic settings
│   │
│   ├── models/                     # Data models
│   │   └── schemas.py             # Pydantic request/response models
│   │
│   └── services/                   # Business logic
│       ├── rag_service.py         # RAG streaming logic
│       ├── qcm_service.py         # QCM generation logic
│       └── course_service.py      # Course generation logic
│
├── rag_engine/                     # RAG implementation
│   └── rag.py                     # Core RAG query logic
│
├── retrivers/                      # Retrieval systems
│   └── hybrid_retriever.py        # BM25 + Vector hybrid search
│
├── qcm_agents/                     # Multi-agent QCM generation
│   ├── orchestrator.py
│   ├── question_generator.py
│   ├── answer_generator.py
│   └── state_manager.py
│
└── course_build_agents/            # Multi-agent course generation
    ├── orchestrator.py
    ├── knowledge_retriever.py
    ├── knowledge_enhancer.py
    └── course_generator.py
```

## Module Responsibilities

### Entry Point (`main.py`)
- Starts uvicorn server with auto-reload
- Loads configuration
- Displays startup banner

### App Factory (`app/main.py`)
- Creates FastAPI application instance
- Configures CORS middleware
- Registers API routers
- Defines root endpoint

### API Routes (`app/api/routes/`)

#### RAG Router (`rag.py`)
- `GET /rag/models` - List available models
- `POST /rag/api/chat/completions` - Chat completions (streaming/non-streaming)

#### Course Router (`course.py`)
- `GET /course/models` - List course generation models
- `POST /course/api/chat/completions` - Generate course (streaming)
- `GET /course/download/{filename}` - Download course files

### Core Components (`app/core/`)

#### Authentication (`auth.py`)
- Bearer token validation
- User authentication dependency
- Token management from environment

### Models (`app/models/`)

#### Schemas (`schemas.py`)
- `ChatMessage` - Individual chat message
- `ChatRequest` - Chat completion request with options

### Services (`app/services/`)

#### RAG Service (`rag_service.py`)
- `stream_rag_response()` - Async generator for streaming RAG responses
- Integrates with rag_engine
- Formats sources and citations

#### Course Service (`course_service.py`)
- `stream_course_generation()` - Async generator for course generation
- Manages multi-agent orchestrator
- Provides heartbeat signals during long operations
- Generates download links

## Configuration Management

### Centralized Settings (`app/core/settings.py`)

All configuration is managed through a Pydantic BaseSettings class:

```python
from app.core.settings import settings

# Access nested settings
url = settings.database.elasticsearch_url
top_k = settings.retriever.top_k

# Check Ollama mode
if settings.ollama.use_cloud:
    # Use cloud client

# Get collection config
collection = settings.get_collection("btp")
```

### Configuration Sources
1. **Environment variables** (highest priority) - loaded from `.env`
2. **config.ini** - Application parameters (backwards compatibility)
3. **Default values** - Defined in settings classes

### Nested Settings Groups
- `settings.database` - Elasticsearch, Qdrant URLs
- `settings.ollama` - Base URL, API key, cloud detection
- `settings.fileserver` - Base URL, public URL
- `settings.retriever` - top_k, weights, RRF settings
- `settings.qcm` - QCM generation parameters
- `settings.course` - Course generation parameters
- `settings.streaming` - Timeouts, heartbeat intervals

### Legacy Support
The old `config_loader.py` is deprecated but still works - it redirects to the new settings module with a deprecation warning.

## Data Flow

### RAG Request Flow
```
Client Request
    ↓
rag.router (authentication)
    ↓
rag_service.stream_rag_response()
    ↓
rag_engine.query_rag()
    ↓
hybrid_retriever.retrieve()
    ↓
[Elasticsearch + Qdrant + Ollama]
    ↓
Stream response to client
```

### Course Generation Flow
```
Client Request
    ↓
course.router (authentication)
    ↓
course_service.stream_course_generation()
    ↓
MultiAgentOrchestratorWithLogging
    ↓
[Knowledge Retriever → Enhancer → Generator]
    ↓
Generate DOCX + Markdown
    ↓
Stream completion with download link
```

## Benefits of This Architecture

1. **Separation of Concerns**
   - Routes handle HTTP
   - Services contain business logic
   - Models define data contracts
   - Core provides shared utilities

2. **Testability**
   - Each module can be tested independently
   - Easy to mock dependencies
   - Clear interfaces between layers

3. **Maintainability**
   - Related code grouped together
   - Easy to locate specific functionality
   - Clear file naming conventions

4. **Scalability**
   - Easy to add new routes
   - Services can be extracted to microservices
   - Clear extension points

5. **Reusability**
   - Services can be used by multiple routes
   - Models shared across application
   - Core utilities available everywhere

## Running the Application

### Development (Local)
```bash
python main.py
```
Auto-reload enabled by default.

### Development (Docker)
```bash
docker-compose up -d
```
Volume mounted for hot-reloading.

### Production
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 4
```

## Adding New Features

### New API Endpoint
1. Create route in `app/api/routes/`
2. Add service logic in `app/services/`
3. Define schemas in `app/models/schemas.py`
4. Register router in `app/main.py`

### New Configuration
1. Add to `app/core/settings.py`:
   - Add field to Settings class with environment variable alias
   - Add to appropriate nested settings class if grouping makes sense
2. Add to `.env.example` (with documentation)
3. Optionally add to `config.ini` for non-sensitive defaults

## Legacy Components

The following are kept for backward compatibility:
- `rag_engine/` - Core RAG logic (used by services)
- `retrivers/` - Search implementations (used by rag_engine)
- `course_build_agents/` - Multi-agent system (used by course service)

These can be gradually refactored into the new structure as needed.
