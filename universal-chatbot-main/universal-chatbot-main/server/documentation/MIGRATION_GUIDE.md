# Migration Guide: From Monolithic to Modular Architecture

## What Changed?

The server has been refactored from a single `rag_server.py` file into a modular structure:

### Old Structure
```
server/
└── rag_server.py (365 lines - everything in one file)
```

### New Structure
```
server/
├── main.py (24 lines - entry point)
└── app/
    ├── main.py (52 lines - app factory)
    ├── api/routes/
    │   ├── rag.py (84 lines)
    │   └── course.py (104 lines)
    ├── core/
    │   └── auth.py (32 lines)
    ├── models/
    │   └── schemas.py (17 lines)
    └── services/
        ├── rag_service.py (83 lines)
        └── course_service.py (93 lines)
```

## What You Need to Do

### Option 1: Keep Old File (Recommended for Safety)

The old `rag_server.py` still exists and will continue to work. You can:

1. **Backup the old file:**
```bash
cp rag_server.py rag_server.py.bak
```

2. **Test the new structure:**
```bash
python main.py
```

3. **Once verified, you can remove the old file:**
```bash
rm rag_server.py
```

### Option 2: Switch Immediately

If you're confident:

1. **Update any scripts** that reference `rag_server.py` to use `main.py`

2. **Update Dockerfile** (already done):
```dockerfile
# Old
CMD ["uvicorn", "rag_server:app", ...]

# New
CMD ["uvicorn", "app.main:app", ...]
```

3. **Update systemd/supervisor configs** if you have them:
```ini
# Old
command=uvicorn rag_server:app --host 0.0.0.0 --port 8080

# New
command=uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Breaking Changes

### None for End Users
- All API endpoints remain the same
- All functionality is identical
- Configuration files unchanged

### For Developers

If you were importing from `rag_server.py`:

```python
# Old imports (no longer work if rag_server.py removed)
from rag_server import app, get_current_user, ChatRequest

# New imports
from app.main import app
from app.core.auth import get_current_user
from app.models.schemas import ChatRequest
```

## Testing the Migration

### 1. Start the Server
```bash
python main.py
```

### 2. Test RAG Endpoint
```bash
curl -H "Authorization: Bearer dev-token-123" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "rag-hybrid",
       "messages": [{"role": "user", "content": "What is RAG?"}],
       "stream": false
     }' \
     http://localhost:8080/rag/api/chat/completions
```

### 3. Test Course Endpoint
```bash
curl -H "Authorization: Bearer dev-token-123" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "course-generator",
       "messages": [{"role": "user", "content": "Machine Learning"}]
     }' \
     http://localhost:8080/course/api/chat/completions
```

### 4. Check Docs
Visit: http://localhost:8080/docs

## Docker Users

### Docker Compose
Already updated - just rebuild:
```bash
docker-compose down
docker-compose up --build -d
```

### Dockerfile
Already updated - rebuild your image:
```bash
docker build -t rag-server .
docker run -p 8080:8080 rag-server
```

## Rollback Plan

If something goes wrong:

### Quick Rollback
```bash
# Stop the new version
# Revert Dockerfile
git checkout Dockerfile

# Use old entry point
python rag_server.py
```

### Docker Rollback
```bash
# Revert docker-compose.yml changes
git checkout docker-compose.yml

# Rebuild
docker-compose up --build -d
```

## Benefits of New Structure

1. **Easier to Navigate**
   - Find RAG code in `app/api/routes/rag.py`
   - Find course code in `app/api/routes/course.py`
   - Clear separation of concerns

2. **Easier to Test**
   - Test routes independently
   - Mock services easily
   - Clear dependencies

3. **Easier to Extend**
   - Add new routes without touching existing ones
   - Reuse services across routes
   - Share models consistently

4. **Better Performance**
   - Smaller modules load faster
   - Better code caching
   - Easier to optimize specific parts

## New File Locations

| Old Location | New Location | What |
|--------------|--------------|------|
| `rag_server.py` (lines 41-52) | `app/models/schemas.py` | Request models |
| `rag_server.py` (lines 57-67) | `app/core/auth.py` | Authentication |
| `rag_server.py` (lines 73-133) | `app/services/rag_service.py` | RAG streaming |
| `rag_server.py` (lines 139-193) | `app/api/routes/rag.py` | RAG endpoints |
| `rag_server.py` (lines 199-307) | `app/api/routes/course.py` | Course endpoints |
| `rag_server.py` (lines 232-297) | `app/services/course_service.py` | Course streaming |
| `rag_server.py` (lines 23-35) | `app/main.py` | CORS & app setup |

## Questions?

- Check `ARCHITECTURE.md` for detailed architecture documentation
- Check `README.md` for usage instructions
- The old `rag_server.py` can serve as reference (if kept)

## Timeline

- **Now**: Both structures work
- **Testing Period**: Use new structure, keep old file as backup
- **After Verification**: Remove old `rag_server.py` file
- **Future**: Gradually refactor `rag_engine/`, `retrivers/`, `course_build_agents/` into app structure

---

## Configuration Migration (config_loader → settings)

The old `config_loader.py` is now deprecated. All configuration is centralized in `app/core/settings.py`.

### Old Import (Deprecated)
```python
from config_loader import settings
```

### New Import (Recommended)
```python
from app.core.settings import settings
```

### New Features
- **Type validation** via Pydantic BaseSettings
- **Nested settings** for organized access: `settings.ollama.base_url`, `settings.qcm.retriever_top_k`
- **Computed properties**: `settings.ollama.use_cloud` automatically detects cloud mode
- **Environment variable binding** with `.env` file support

### Backwards Compatibility
- Old property names still work: `settings.ELASTICSEARCH_URL`, `settings.RETRIEVER_TOP_K`
- `config_loader.py` still works but shows deprecation warning
- `config.ini` is still loaded for non-sensitive defaults
