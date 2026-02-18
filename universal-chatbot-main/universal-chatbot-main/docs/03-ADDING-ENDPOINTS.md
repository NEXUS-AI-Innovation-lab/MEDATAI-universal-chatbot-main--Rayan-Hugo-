# Adding New Endpoints to the Server

This guide explains how to add new API endpoints to the RAG server.

---

## Architecture Overview

The server follows a layered architecture:

```
app/
├── api/
│   └── routes/          # API endpoint handlers
│       ├── rag.py       # /rag/api/*
│       ├── course.py    # /course/api/*
│       └── qcm.py       # /qcm/api/*
├── services/            # Business logic
│   ├── rag_service.py
│   ├── course_service.py
│   └── qcm_service.py
├── models/
│   └── schemas.py       # Pydantic models
├── core/
│   └── auth.py          # Authentication
└── main.py              # FastAPI app factory
```

---

## Step 1: Create the Route File

Create a new file in `app/api/routes/`:

```python
# app/api/routes/myfeature.py

"""
My Feature endpoints router
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from datetime import datetime
import uuid

from app.models.schemas import ChatRequest
from app.core.auth import get_current_user
from app.services.myfeature_service import stream_myfeature_response
from config_loader import settings

# Create router with prefix and tags
router = APIRouter(prefix="/myfeature", tags=["My Feature"])


@router.get("/api/models")
async def myfeature_models(current_user: dict = Depends(get_current_user)):
    """List available collections for this feature."""
    created = int(datetime.now().timestamp())
    return {
        "object": "list",
        "data": [
            {
                "id": name,
                "object": "model",
                "created": created,
                "owned_by": "custom"
            }
            for name in settings.COLLECTIONS.keys()
        ]
    }


@router.post("/api/chat/completions")
async def myfeature_chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    My Feature chat completion endpoint.

    Describe what this endpoint does here.
    """
    # Extract user messages
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    # Validate collection
    collection_name = request.model
    if not collection_name or collection_name not in settings.COLLECTIONS:
        available = list(settings.COLLECTIONS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection '{collection_name}'. Available: {available}"
        )

    # Get the user's input
    user_input = user_messages[-1].content.strip()

    if not user_input:
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Please provide input."},
                "finish_reason": "stop"
            }]
        }

    # Return streaming response
    return StreamingResponse(
        stream_myfeature_response(user_input, collection_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
```

---

## Step 2: Create the Service Layer

Create the service file in `app/services/`:

```python
# app/services/myfeature_service.py

"""
My Feature service layer
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator

from config_loader import settings


async def stream_myfeature_response(
    user_input: str,
    collection_name: str
) -> AsyncGenerator[str, None]:
    """
    Stream the feature response.

    Args:
        user_input: User's input text
        collection_name: Collection to use for RAG

    Yields:
        str: Server-sent events formatted response chunks
    """
    message_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_timestamp = int(datetime.now().timestamp())

    def make_chunk(content: str = "", reasoning: str = "", finish: bool = False):
        """Helper to create SSE chunks."""
        delta = {}
        if content:
            delta["content"] = content
        if reasoning:
            delta["role"] = "assistant"
            delta["reasoning_content"] = reasoning

        return {
            "id": message_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": collection_name,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": "stop" if finish else None
            }]
        }

    try:
        # Send progress/thinking updates (appears in thinking box)
        yield f"data: {json.dumps(make_chunk(reasoning='Processing your request...'))}\n\n"

        # Your actual processing logic here
        # Example: Call RAG, process data, generate response

        # Simulate some processing
        await asyncio.sleep(0.1)

        # Stream the response content
        response_text = f"Processed your input: {user_input}"

        # Stream in chunks for smooth display
        chunk_size = settings.RAG_CHUNK_SIZE if hasattr(settings, 'RAG_CHUNK_SIZE') else 5
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i:i + chunk_size]
            yield f"data: {json.dumps(make_chunk(content=chunk))}\n\n"
            await asyncio.sleep(0.01)

        # Send finish signal
        yield f"data: {json.dumps(make_chunk(finish=True))}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        # Send error
        error_chunk = make_chunk(content=f"\n\nError: {str(e)}")
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"
```

---

## Step 3: Register the Router

Edit `app/main.py` to include your new router:

```python
# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import rag, course, qcm, myfeature  # Add import

def create_app() -> FastAPI:
    app = FastAPI(
        title="Universal RAG Server",
        description="RAG, Course Generation, QCM, and more",
        version="1.0.0"
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(rag.router)
    app.include_router(course.router)
    app.include_router(qcm.router)
    app.include_router(myfeature.router)  # Add this line

    return app

app = create_app()
```

---

## Step 4: Using RAG in Your Endpoint

To use the RAG system in your feature:

```python
# In your service file

from rag_engine.rag import context_from_query, query_rag, stream_rag_with_thinking

async def stream_myfeature_response(user_input: str, collection_name: str):
    # Option 1: Get raw context (chunks + sources)
    knowledge_base, sources = context_from_query(
        query=user_input,
        collection_name=collection_name,
        top_k=5
    )

    # Option 2: Full RAG query (context + LLM response)
    answer, used_sources = query_rag(
        question=user_input,
        collection_name=collection_name,
        top_k=5
    )

    # Option 3: Streaming RAG with thinking
    for update in stream_rag_with_thinking(user_input, collection_name, top_k=5):
        if update['type'] == 'thinking':
            # LLM is generating (raw tokens)
            yield make_thinking_chunk(update['content'])
        elif update['type'] == 'final':
            # Final answer with citations
            yield make_content_chunk(update['content'])
```

---

## Step 5: Add to LibreChat Configuration

Update `front/librechat.yaml`:

```yaml
endpoints:
  custom:
    # ... existing endpoints ...

    - name: "My Feature"
      apiKey: "${CUSTOM_API_KEY}"
      baseURL: "http://universal-rag-server:8080/myfeature/api"
      models:
        default:
          - "${DEFAULT_COLLECTION}"
        fetch: true
      titleConvo: true
      titleModel: "${DEFAULT_COLLECTION}"
      modelDisplayLabel: "My Feature"
      iconURL: "https://cdn-icons-png.flaticon.com/512/your-icon.png"
      type: "openai"
      dropParams: ["user"]
      context: 8000
      max_tokens: 4096
```

---

## Common Patterns

### Pattern 1: Simple Request-Response

```python
@router.post("/api/chat/completions")
async def simple_endpoint(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    # Process
    result = process_input(request.messages[-1].content)

    # Return non-streaming response
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result},
            "finish_reason": "stop"
        }]
    }
```

### Pattern 2: Streaming with Progress

```python
async def stream_with_progress(input_text: str, collection_name: str):
    # Phase 1: Show progress
    yield make_sse_chunk(reasoning="Step 1: Analyzing input...")
    result1 = await step1(input_text)

    yield make_sse_chunk(reasoning="Step 2: Retrieving context...")
    result2 = await step2(result1, collection_name)

    yield make_sse_chunk(reasoning="Step 3: Generating response...")
    result3 = await step3(result2)

    # Phase 2: Stream final content
    for chunk in split_into_chunks(result3):
        yield make_sse_chunk(content=chunk)

    yield make_sse_chunk(finish=True)
    yield "data: [DONE]\n\n"
```

### Pattern 3: Multi-Agent Workflow

```python
from course_build_agents.utils import context_from_query, call_llm

async def multi_agent_stream(subject: str, collection_name: str):
    # Agent 1: Research
    yield make_sse_chunk(reasoning="Agent 1: Researching...")
    knowledge, sources = context_from_query(subject, collection_name, top_k=10)

    # Agent 2: Analyze
    yield make_sse_chunk(reasoning="Agent 2: Analyzing...")
    analysis = call_llm(
        system_prompt="Analyze the following knowledge...",
        user_prompt=knowledge
    )

    # Agent 3: Generate
    yield make_sse_chunk(reasoning="Agent 3: Generating output...")
    final = call_llm(
        system_prompt="Create final output from analysis...",
        user_prompt=analysis
    )

    # Stream result
    for chunk in split_into_chunks(final):
        yield make_sse_chunk(content=chunk)
```

---

## SSE Response Format

All streaming responses must follow the Server-Sent Events format:

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":123,"model":"btp","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":123,"model":"btp","choices":[{"index":0,"delta":{"content":" world"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":123,"model":"btp","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### Delta Fields

| Field | Purpose |
|-------|---------|
| `content` | Main response text (displayed to user) |
| `reasoning_content` | Thinking/progress (shown in thinking box) |
| `role` | Always "assistant" |

---

## Testing Your Endpoint

### With curl:

```bash
# Test models endpoint
curl http://localhost:8080/myfeature/api/models \
  -H "Authorization: Bearer dev-token-123"

# Test chat endpoint (non-streaming)
curl -X POST http://localhost:8080/myfeature/api/chat/completions \
  -H "Authorization: Bearer dev-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "btp",
    "messages": [{"role": "user", "content": "Test input"}],
    "stream": false
  }'

# Test chat endpoint (streaming)
curl -X POST http://localhost:8080/myfeature/api/chat/completions \
  -H "Authorization: Bearer dev-token-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "btp",
    "messages": [{"role": "user", "content": "Test input"}],
    "stream": true
  }'
```

### With Python:

```python
import requests

# Test models
response = requests.get(
    "http://localhost:8080/myfeature/api/models",
    headers={"Authorization": "Bearer dev-token-123"}
)
print(response.json())

# Test streaming
response = requests.post(
    "http://localhost:8080/myfeature/api/chat/completions",
    headers={
        "Authorization": "Bearer dev-token-123",
        "Content-Type": "application/json"
    },
    json={
        "model": "btp",
        "messages": [{"role": "user", "content": "Test"}],
        "stream": True
    },
    stream=True
)

for line in response.iter_lines():
    if line:
        print(line.decode())
```

---

## Checklist for New Endpoints

- [ ] Create route file in `app/api/routes/`
- [ ] Create service file in `app/services/`
- [ ] Register router in `app/main.py`
- [ ] Implement `/api/models` endpoint
- [ ] Implement `/api/chat/completions` endpoint
- [ ] Add authentication (`Depends(get_current_user)`)
- [ ] Validate collection name against `settings.COLLECTIONS`
- [ ] Return OpenAI-compatible response format
- [ ] Add to LibreChat configuration
- [ ] Test with curl and in LibreChat UI
