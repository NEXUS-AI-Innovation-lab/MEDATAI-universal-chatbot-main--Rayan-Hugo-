# RAG & Course Generation Server

A FastAPI-based server that provides RAG (Retrieval-Augmented Generation) capabilities and automated course generation using a multi-agent system.

## Features

- **RAG System**: Hybrid retrieval using BM25 and vector search with Ollama LLM
- **Course Generation**: Multi-agent system for automated course content creation
- **Streaming Responses**: Real-time streaming for both RAG and course generation
- **Document Export**: Generates courses in Markdown and Word (DOCX) formats

## Configuration

The application uses two configuration sources:

### 1. config.ini (Application Parameters)

Contains non-sensitive application parameters:
- Server settings (host, port, log level)
- CORS configuration
- RAG parameters (model, chunk size, temperature)
- Hybrid retriever settings (weights, top-k values)
- Course generation parameters
- File paths and directories

### 2. .env (Environment Variables for APIs)

Contains sensitive API connections and credentials:

```bash
# Copy the example file
cp .env.example .env

# Edit .env with your actual values
```

Required environment variables:
- `ELASTICSEARCH_URL`: Elasticsearch endpoint
- `ELASTICSEARCH_INDEX`: Index name for BM25 search
- `QDRANT_URL`: Qdrant vector database endpoint
- `QDRANT_COLLECTION`: Collection name for vector search
- `OLLAMA_BASE_URL`: Ollama API endpoint
- `AUTH_TOKENS`: Authentication tokens (format: token:user_id:name)
- `SERVER_BASE_URL`: Base URL for download links

## Installation

### Local Development

1. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

2. **Download spaCy French model**:
```bash
python -m spacy download fr_core_news_sm
```

3. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your actual values
```

4. **Run the server**:
```bash
python main.py
```

The server will start at `http://localhost:8080` with auto-reload enabled

### Docker Development (Recommended)

The Docker setup includes hot-reloading - any file changes will automatically restart the server.

1. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your actual values
```

2. **Start all services**:
```bash
docker-compose up -d
```

This will start:
- RAG Server (port 8080) - with mounted volume for hot-reloading
- Elasticsearch (port 9200)
- Qdrant (port 6333)
- Ollama (port 11434)

3. **View logs**:
```bash
docker-compose logs -f rag-server
```

4. **Stop services**:
```bash
docker-compose down
```

5. **Rebuild after dependency changes**:
```bash
docker-compose up -d --build
```

## API Endpoints

### RAG Endpoints

- `GET /rag/models` - List available RAG models
- `POST /rag/api/chat/completions` - RAG chat completion (streaming/non-streaming)

### Course Generation Endpoints

- `GET /course/models` - List available course generation models
- `POST /course/api/chat/completions` - Generate course (streaming)
- `GET /course/download/{filename}` - Download generated course files

### Documentation

- `GET /` - API status
- `GET /docs` - Interactive API documentation (Swagger UI)

## Development

### Hot-Reloading

When using Docker Compose, the current directory is mounted as a volume. Any changes to Python files will trigger an automatic reload of the server.

### File Structure

```
server/
├── config.ini                      # Application configuration (non-sensitive)
├── .env                            # Environment variables (not in git)
├── .env.example                   # Environment variables template
├── collections.json               # Collection registry (qdrant/es mappings)
├── config_loader.py               # DEPRECATED - redirects to app.core.settings
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Docker image definition
├── docker-compose.yml             # Docker Compose configuration
├── main.py                        # Server entry point
├── app/                           # Main application package
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory
│   ├── api/                       # API layer
│   │   ├── __init__.py
│   │   └── routes/                # API route modules
│   │       ├── __init__.py
│   │       ├── rag.py            # RAG endpoints
│   │       ├── qcm.py            # QCM endpoints
│   │       └── course.py         # Course endpoints
│   ├── core/                      # Core components
│   │   ├── __init__.py
│   │   ├── auth.py               # Authentication
│   │   └── settings.py           # Centralized Pydantic settings
│   ├── models/                    # Data models
│   │   ├── __init__.py
│   │   └── schemas.py            # Pydantic schemas
│   └── services/                  # Business logic
│       ├── __init__.py
│       ├── rag_service.py        # RAG streaming service
│       ├── qcm_service.py        # QCM generation service
│       └── course_service.py     # Course generation service
├── rag_engine/                    # RAG engine
│   └── rag.py
├── retrivers/                     # Retrieval systems
│   └── hybrid_retriever.py
├── qcm_agents/                    # QCM multi-agent system
│   ├── orchestrator.py
│   ├── question_generator.py
│   ├── answer_generator.py
│   └── state_manager.py
└── course_build_agents/           # Course multi-agent system
    ├── orchestrator.py
    ├── orchestrator_with_logging.py
    ├── knowledge_retriever.py
    ├── knowledge_enhancer.py
    ├── course_generator.py
    └── utils.py
```

## Authentication

The API uses Bearer token authentication. Configure tokens in the `.env` file:

```bash
AUTH_TOKENS=your-token:user_id:User Name,another-token:user2:Another User
```

Include the token in requests:
```bash
curl -H "Authorization: Bearer your-token" http://localhost:8080/rag/models
```

## Customization

### Changing Parameters

Edit `config.ini` to modify:
- Server host/port
- RAG model and parameters
- Retriever weights and top-k values
- Course generation iterations
- Output directories

### Changing API Endpoints

Edit `.env` to point to different services:
```bash
ELASTICSEARCH_URL=http://your-elasticsearch:9200
QDRANT_URL=http://your-qdrant:6333
OLLAMA_BASE_URL=http://your-ollama:11434
```

## Troubleshooting

### Port Conflicts

If ports are already in use, modify them in `docker-compose.yml`:
```yaml
ports:
  - "8081:8080"  # Change 8081 to any available port
```

### Module Import Errors

Ensure you're running from the server directory:
```bash
cd server
python rag_server.py
```

### Configuration Not Loading

1. Verify `config.ini` exists in the server directory
2. Check `.env` file is present and properly formatted
3. Ensure no syntax errors in configuration files

## License

[Your License Here]
