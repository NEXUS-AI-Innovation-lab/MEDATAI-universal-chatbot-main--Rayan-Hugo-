# LibreChat Custom Server Setup

This guide explains how to configure LibreChat to use your custom RAG server as a backend.

---

## Overview

LibreChat is an open-source chat UI that supports custom OpenAI-compatible endpoints. Your RAG server exposes three endpoints that LibreChat can connect to:

| Endpoint | Base URL | Purpose |
|----------|----------|---------|
| RAG | `/rag/api` | Question answering with sources |
| Course | `/course/api` | Course generation |
| QCM | `/qcm/api` | Quiz generation |

---

## Configuration Files

LibreChat uses two main configuration files:

1. **`.env`** - Environment variables (secrets, URLs)
2. **`librechat.yaml`** - Endpoint configuration

Both files should be in your LibreChat directory (e.g., `front/`).

---

## Step 1: Environment Variables (.env)

Create or edit the `.env` file:

```bash
# =================================================================
# CORE CONFIGURATION
# =================================================================
HOST=0.0.0.0
PORT=3080

# =================================================================
# DATABASE
# =================================================================
MONGO_URI=mongodb://mongodb:27017/LibreChat

# =================================================================
# SEARCH (MeiliSearch)
# =================================================================
MEILI_HOST=http://meilisearch:7700
MEILI_NO_ANALYTICS=true

# =================================================================
# SECURITY - CHANGE THESE IN PRODUCTION!
# =================================================================
# Generate new secrets with: openssl rand -base64 64
JWT_SECRET=your-jwt-secret-here
JWT_REFRESH_SECRET=your-refresh-secret-here
CREDS_KEY=your-32-byte-hex-key
CREDS_IV=your-16-byte-hex-iv

# =================================================================
# SESSION
# =================================================================
SESSION_EXPIRY=900000
REFRESH_TOKEN_EXPIRY=604800000

# =================================================================
# CUSTOM API (Your RAG Server)
# =================================================================
# API key that matches your server's AUTH_TOKENS
CUSTOM_API_KEY=dev-token-123

# Default collection name (must exist in collections.json)
DEFAULT_COLLECTION=btp

# =================================================================
# APP SETTINGS
# =================================================================
APP_TITLE=My RAG System
ALLOW_REGISTRATION=true
ALLOW_SOCIAL_LOGIN=false
```

**Important variables:**
- `CUSTOM_API_KEY`: Must match a token in your server's `AUTH_TOKENS` environment variable
- `DEFAULT_COLLECTION`: The default collection shown in dropdowns (must exist)

---

## Step 2: Endpoint Configuration (librechat.yaml)

Create or edit the `librechat.yaml` file:

```yaml
version: 1.1.7

cache: true

endpoints:
  custom:
    # ===========================================
    # RAG Hybrid Search Endpoint
    # ===========================================
    - name: "RAG Hybrid"
      apiKey: "${CUSTOM_API_KEY}"
      baseURL: "http://universal-rag-server:8080/rag/api"
      models:
        default:
          - "${DEFAULT_COLLECTION}"
        fetch: true
      titleConvo: true
      titleModel: "${DEFAULT_COLLECTION}"
      summarize: false
      forcePrompt: false
      modelDisplayLabel: "RAG Hybrid"
      iconURL: "https://cdn-icons-png.flaticon.com/512/4712/4712027.png"
      type: "openai"
      dropParams: ["user"]
      context: 8000
      max_tokens: 4096

    # ===========================================
    # Course Generator Endpoint
    # ===========================================
    - name: "Course Generator"
      apiKey: "${CUSTOM_API_KEY}"
      baseURL: "http://universal-rag-server:8080/course/api"
      models:
        default:
          - "${DEFAULT_COLLECTION}"
        fetch: true
      titleConvo: true
      titleModel: "${DEFAULT_COLLECTION}"
      summarize: false
      forcePrompt: false
      modelDisplayLabel: "Course Generator"
      iconURL: "https://cdn-icons-png.flaticon.com/512/2602/2602414.png"
      type: "openai"
      dropParams: ["user", "stream", "frequency_penalty", "presence_penalty", "top_p"]
      addParams:
        stream: false
      context: 8000
      max_tokens: 8000

    # ===========================================
    # QCM (Quiz) Generator Endpoint
    # ===========================================
    - name: "QCM Generator"
      apiKey: "${CUSTOM_API_KEY}"
      baseURL: "http://universal-rag-server:8080/qcm/api"
      models:
        default:
          - "${DEFAULT_COLLECTION}"
        fetch: true
      titleConvo: true
      titleModel: "${DEFAULT_COLLECTION}"
      summarize: false
      forcePrompt: false
      modelDisplayLabel: "QCM Generator"
      iconURL: "https://cdn-icons-png.flaticon.com/512/3176/3176298.png"
      type: "openai"
      dropParams: ["user"]
      context: 8000
      max_tokens: 8000

# ===========================================
# Interface Settings
# ===========================================
interface:
  modelSelect: true        # Show model/collection dropdown
  parameters: false        # Hide parameter controls
  sidePanel: false
  presets: false
  prompts: false
  bookmarks: true
  multiConvo: false
  agents: false
  customWelcome: "Welcome to the RAG System!"
  runCode: false
  webSearch: false
  fileSearch: false
  fileCitations: false

# ===========================================
# File Upload (Disabled for RAG endpoints)
# ===========================================
fileConfig:
  endpoints:
    "RAG Hybrid":
      disabled: true
    "Course Generator":
      disabled: true
    "QCM Generator":
      disabled: true
```

---

## Step 3: Understanding Configuration Options

### Endpoint Options

| Option | Description |
|--------|-------------|
| `name` | Display name in LibreChat UI |
| `apiKey` | Authentication token (use env variable) |
| `baseURL` | Your server's endpoint URL |
| `models.default` | Default model/collection shown |
| `models.fetch` | Fetch available models from `/api/models` |
| `titleConvo` | Auto-generate conversation titles |
| `titleModel` | Model to use for title generation |
| `type` | API format (`openai` for OpenAI-compatible) |
| `dropParams` | Parameters to exclude from requests |
| `addParams` | Parameters to always include |
| `iconURL` | Custom icon for the endpoint |

### Interface Options

| Option | Description |
|--------|-------------|
| `modelSelect` | Show collection dropdown |
| `parameters` | Show temperature/top_p controls |
| `bookmarks` | Enable conversation bookmarks |
| `customWelcome` | Custom welcome message |

---

## Step 4: Docker Compose Setup

Example `docker-compose.yml` for LibreChat with your RAG server:

```yaml
version: '3.8'

services:
  # LibreChat Frontend
  librechat:
    image: ghcr.io/danny-avila/librechat:latest
    container_name: librechat
    ports:
      - "3080:3080"
    env_file:
      - .env
    volumes:
      - ./librechat.yaml:/app/librechat.yaml:ro
    depends_on:
      - mongodb
      - meilisearch
      - universal-rag-server
    networks:
      - app-network

  # Your RAG Server
  universal-rag-server:
    build:
      context: ./server
      dockerfile: Dockerfile
    container_name: universal-rag-server
    environment:
      - AUTH_TOKENS=dev-token-123:user_1:Developer
      - ELASTICSEARCH_URL=http://elasticsearch:9200
      - QDRANT_URL=http://qdrant:6333
      - OLLAMA_BASE_URL=http://ollama:11434
      - FILESERVER_BASE=http://fileserver:8000
      - FILESERVER_PUBLIC_URL=http://localhost:7700
    volumes:
      - ./server:/app
      - ./storage:/storage
    networks:
      - app-network

  # MongoDB for LibreChat
  mongodb:
    image: mongo:6
    container_name: mongodb
    volumes:
      - ./storage/mongodb:/data/db
    networks:
      - app-network

  # MeiliSearch for LibreChat
  meilisearch:
    image: getmeili/meilisearch:latest
    container_name: meilisearch
    environment:
      - MEILI_NO_ANALYTICS=true
    volumes:
      - ./storage/meilisearch:/meili_data
    networks:
      - app-network

  # Qdrant Vector Database
  qdrant:
    image: qdrant/qdrant:latest
    container_name: qdrant
    volumes:
      - ./storage/qdrant:/qdrant/storage
    networks:
      - app-network

  # Elasticsearch
  elasticsearch:
    image: elasticsearch:8.11.0
    container_name: elasticsearch
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    volumes:
      - ./storage/elasticsearch:/usr/share/elasticsearch/data
    networks:
      - app-network

  # Ollama LLM
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    volumes:
      - ./storage/ollama:/root/.ollama
    networks:
      - app-network

  # Fileserver
  fileserver:
    build:
      context: ./fileserver
      dockerfile: Dockerfile
    container_name: fileserver
    ports:
      - "7700:8000"
    volumes:
      - ./storage/raw_data:/data
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

---

## Step 5: Network Configuration

When running in Docker, services communicate via container names:

| From LibreChat | URL |
|----------------|-----|
| RAG Server | `http://universal-rag-server:8080` |
| MongoDB | `mongodb://mongodb:27017` |
| MeiliSearch | `http://meilisearch:7700` |

When accessing from browser:

| Service | URL |
|---------|-----|
| LibreChat UI | `http://localhost:3080` |
| Fileserver (for PDF links) | `http://localhost:7700` |

---

## Step 6: Adding a New Custom Endpoint

To add a new endpoint to LibreChat, add a new entry under `endpoints.custom`:

```yaml
endpoints:
  custom:
    # ... existing endpoints ...

    # New Custom Endpoint
    - name: "My New Feature"
      apiKey: "${CUSTOM_API_KEY}"
      baseURL: "http://universal-rag-server:8080/myfeature/api"
      models:
        default:
          - "${DEFAULT_COLLECTION}"
        fetch: true
      titleConvo: true
      titleModel: "${DEFAULT_COLLECTION}"
      modelDisplayLabel: "My Feature"
      iconURL: "https://example.com/icon.png"
      type: "openai"
      dropParams: ["user"]
```

Then implement the `/myfeature/api/models` and `/myfeature/api/chat/completions` endpoints on your server.

---

## Troubleshooting

### "Endpoint not showing in LibreChat"
1. Check `librechat.yaml` syntax (use YAML validator)
2. Restart LibreChat container
3. Check container logs: `docker logs librechat`

### "Authentication failed"
1. Verify `CUSTOM_API_KEY` in `.env` matches `AUTH_TOKENS` on server
2. Check the token format: `token:user_id:name`

### "No models in dropdown"
1. Ensure `DEFAULT_COLLECTION` is set and valid
2. Check server's `/api/models` endpoint works:
   ```bash
   curl http://localhost:8080/rag/api/models \
     -H "Authorization: Bearer dev-token-123"
   ```

### "Conversation titles not generating"
1. Ensure `titleConvo: true` is set
2. Ensure `titleModel` points to a valid collection
3. The endpoint must return valid responses for title generation

### "Connection refused"
1. Check Docker network connectivity
2. Verify service names in `baseURL` match container names
3. Check if RAG server is running: `docker logs universal-rag-server`

---

## Security Recommendations

For production:

1. **Change all secrets** in `.env`:
   ```bash
   # Generate new secrets
   openssl rand -base64 64  # For JWT secrets
   openssl rand -hex 32     # For CREDS_KEY
   openssl rand -hex 16     # For CREDS_IV
   ```

2. **Use strong API tokens**:
   ```bash
   # Generate secure token
   openssl rand -hex 32
   ```

3. **Enable HTTPS** via reverse proxy (nginx, traefik)

4. **Restrict network access** - don't expose internal services

5. **Set `ALLOW_REGISTRATION=false`** after creating admin accounts
