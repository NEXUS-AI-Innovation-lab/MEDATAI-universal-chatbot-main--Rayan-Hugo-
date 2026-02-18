# Quick Start Guide

Get your RAG system up and running in minutes.

---

## Prerequisites

- Docker & Docker Compose
- Python 3.10+
- Mistral API key (for PDF processing)

---

## 1. Clone and Start Services

```bash
# Start all services
docker-compose up -d

# Wait for services to be ready (about 30 seconds)
docker-compose logs -f
```

Services started:
- LibreChat UI: http://localhost:3080
- RAG Server: http://localhost:8080
- Fileserver: http://localhost:7700

---

## 2. Create Your First Collection

```bash
cd digest/

# Install dependencies (first time only)
pip install -r requirements.txt
python -m spacy download fr_core_news_sm

# Create a collection from your documents
python digest.py create my_docs /path/to/your/pdfs --mistral-key sk-xxxxx
```

---

## 3. Configure LibreChat

Edit `front/.env`:
```bash
DEFAULT_COLLECTION=my_docs
CUSTOM_API_KEY=dev-token-123
```

Restart LibreChat:
```bash
docker-compose restart librechat
```

---

## 4. Start Using

1. Open http://localhost:3080
2. Create an account
3. Select "RAG Hybrid" from the sidebar
4. Choose your collection from the dropdown
5. Ask questions!

---

## Available Features

| Endpoint | What it does |
|----------|--------------|
| **RAG Hybrid** | Question answering with sources |
| **Course Generator** | Create structured courses |
| **QCM Generator** | Generate quizzes |

---

## Next Steps

- [Collections Guide](01-COLLECTIONS-GUIDE.md) - Add more documents
- [LibreChat Setup](02-LIBRECHAT-SETUP.md) - Customize the UI
- [Adding Endpoints](03-ADDING-ENDPOINTS.md) - Extend functionality

---

## Troubleshooting

**No models in dropdown:**
```bash
# Check collection exists
python digest/digest.py list

# Check server is running
curl http://localhost:8080/rag/api/models -H "Authorization: Bearer dev-token-123"
```

**Connection refused:**
```bash
# Check all services are running
docker-compose ps

# Check logs
docker-compose logs universal-rag-server
```

**PDF processing fails:**
- Verify Mistral API key is valid
- Check https://console.mistral.ai/ for credits
