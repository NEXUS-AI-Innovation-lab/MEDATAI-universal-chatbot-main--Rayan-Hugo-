# [WIP] Universal RAG System Documentation

Welcome to the documentation for the Universal RAG System - a hybrid search RAG platform with course and quiz generation capabilities.

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [00-QUICK-START.md](00-QUICK-START.md) | Get up and running in 5 minutes |
| [01-COLLECTIONS-GUIDE.md](01-COLLECTIONS-GUIDE.md) | Creating and managing document collections |
| [02-LIBRECHAT-SETUP.md](02-LIBRECHAT-SETUP.md) | Configuring LibreChat frontend |
| [03-ADDING-ENDPOINTS.md](03-ADDING-ENDPOINTS.md) | Adding new API endpoints |
| [04-ARCHITECTURE.md](04-ARCHITECTURE.md) | System architecture overview |
| [05-CONFIGURATION-REFERENCE.md](05-CONFIGURATION-REFERENCE.md) | All configuration options |

---

## Quick Links

### I want to...

| Goal | Document |
|------|----------|
| Start using the system | [Quick Start](00-QUICK-START.md) |
| Add documents to search | [Collections Guide](01-COLLECTIONS-GUIDE.md) |
| Set up the web interface | [LibreChat Setup](02-LIBRECHAT-SETUP.md) |
| Build a new feature | [Adding Endpoints](03-ADDING-ENDPOINTS.md) |
| Understand how it works | [Architecture](04-ARCHITECTURE.md) |
| Tune performance | [Configuration Reference](05-CONFIGURATION-REFERENCE.md) |

---

## System Overview

```
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│   LibreChat    │────▶│   RAG Server   │────▶│  Qdrant + ES   │
│   (Frontend)   │     │   (FastAPI)    │     │  (Search DBs)  │
└────────────────┘     └────────────────┘     └────────────────┘
                              │
                              ▼
                       ┌────────────────┐
                       │     Ollama     │
                       │     (LLM)      │
                       └────────────────┘
```

---

## Features

- **Hybrid Search**: Combines semantic (vector) and keyword (BM25) search
- **Multi-Collection**: Support multiple knowledge bases
- **RAG Chat**: Question answering with source citations
- **Course Generation**: Multi-agent course creation
- **Quiz Generation**: Automatic QCM generation
- **Streaming**: Real-time response streaming
- **OpenAI Compatible**: Works with any OpenAI-compatible client

---

## Support

For issues and questions:
1. Check the relevant documentation
2. Review container logs: `docker-compose logs <service>`
3. Open an issue on GitHub

---

## License

