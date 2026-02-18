"""
FastAPI RAG Server for LibreChat Integration
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import json
import asyncio
import uuid
import os

from rag_engine.rag import query_rag
from course_build_agents.orchestrator_with_logging import MultiAgentOrchestratorWithLogging
from config_loader import settings

# ==========================================================
# FASTAPI APP SETUP
# ==========================================================

app = FastAPI(
    title="RAG Server for LibreChat",
    description="RAG and Course Generation API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS if settings.CORS_ALLOW_ORIGINS != ['*'] else ["*"],
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS if settings.CORS_ALLOW_METHODS != ['*'] else ["*"],
    allow_headers=settings.CORS_ALLOW_HEADERS if settings.CORS_ALLOW_HEADERS != ['*'] else ["*"],
)

# ==========================================================
# MODELS
# ==========================================================

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "rag-hybrid"
    messages: List[ChatMessage]
    stream: bool = True
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    top_k: Optional[int] = 5

# ==========================================================
# AUTH
# ==========================================================

VALID_TOKENS = settings.get_auth_tokens()

async def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    token = authorization.replace("Bearer ", "")
    if token not in VALID_TOKENS:
        raise HTTPException(status_code=401, detail="Invalid token")
    return VALID_TOKENS[token]

# ==========================================================
# RAG STREAMING
# ==========================================================

async def stream_rag_response(question: str, top_k: int = 5, model: str = "rag-hybrid"):
    try:
        message_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created_timestamp = int(datetime.now().timestamp())

        loop = asyncio.get_event_loop()
        answer_with_links, used_sources = await loop.run_in_executor(
            None, query_rag, question, top_k
        )

        if used_sources:
            sources_text = "\n\n**Sources:**\n"
            for idx, source in enumerate(used_sources, 1):
                sources_text += f"{idx}. [{source['title']}]({source['url']})\n"
            answer_with_links += sources_text

        chunk_size = settings.RAG_CHUNK_SIZE
        for i in range(0, len(answer_with_links), chunk_size):
            chunk = answer_with_links[i:i+chunk_size]
            chunk_data = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": created_timestamp,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": chunk},
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"
            await asyncio.sleep(settings.RAG_CHUNK_DELAY)

        final_chunk = {
            "id": message_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        error_chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "created": int(datetime.now().timestamp()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n\nError: {str(e)}"},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"

# ==========================================================
# RAG ENDPOINTS (under /rag)
# ==========================================================

@app.get("/rag/models")
async def rag_models(current_user: dict = Depends(get_current_user)):
    return {
        "object": "list",
        "data": [{
            "id": "rag-hybrid",
            "object": "model",
            "created": int(datetime.now().timestamp()),
            "owned_by": "custom"
        }]
    }

@app.post("/rag/api/chat/completions")
async def rag_chat(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    question = user_messages[-1].content
    top_k = request.top_k or settings.RAG_DEFAULT_TOP_K

    if request.stream:
        return StreamingResponse(
            stream_rag_response(question, top_k, request.model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        answer_with_links, used_sources = query_rag(question, top_k=top_k)
        if used_sources:
            sources_text = "\n\n**Sources:**\n"
            for idx, source in enumerate(used_sources, 1):
                sources_text += f"{idx}. [{source['title']}]({source['url']})\n"
            answer_with_links += sources_text

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": answer_with_links},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(question.split()),
                "completion_tokens": len(answer_with_links.split()),
                "total_tokens": len(question.split()) + len(answer_with_links.split())
            }
        }

# ==========================================================
# COURSE ENDPOINTS (under /course)
# ==========================================================

@app.get("/course/models")
async def course_models(current_user: dict = Depends(get_current_user)):
    return {
        "object": "list",
        "data": [{
            "id": "course-generator",
            "object": "model",
            "created": int(datetime.now().timestamp()),
            "owned_by": "custom"
        }]
    }


@app.post("/course/api/chat/completions")
async def course_chat(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="Aucun message utilisateur trouvé")

    subject = user_messages[-1].content.strip()
    if not subject:
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": request.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Veuillez fournir un sujet pour le cours."},
                "finish_reason": "stop"
            }]
        }

    # ---- STREAMING WITH HEARTBEATS ----
    async def heartbeat_stream():
        message_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created_timestamp = int(datetime.now().timestamp())

        # Prepare orchestrator & paths
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(settings.COURSE_OUTPUT_BASE_DIR, f"{subject.replace(' ', '_')}_{timestamp}")

        config = {
            'retriever_top_k': settings.COURSE_RETRIEVER_TOP_K,
            'enhancer_iterations': settings.COURSE_ENHANCER_ITERATIONS,
            'enhancer_top_k': settings.COURSE_ENHANCER_TOP_K,
            'output_dir': output_dir,
            'enable_logging': settings.COURSE_ENABLE_LOGGING
        }

        orchestrator = MultiAgentOrchestratorWithLogging(config)

        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, orchestrator.run, subject)

        # HEARTBEAT LOOP (configurable interval)
        while not task.done():
            heartbeat = {
                "id": message_id,
                "object": "chat.completion.chunk",
                "created": created_timestamp,
                "model": request.model,
                "choices": [{
                    "index": 0,
                    "delta": {},        # empty delta = no display for user
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(heartbeat)}\n\n"
            await asyncio.sleep(settings.COURSE_HEARTBEAT_INTERVAL)

        # ---- FINAL RESULT ----
        results = await task

        download_link = f"{settings.SERVER_BASE_URL}/course/download/{results.get('course_docx_path')}"

        final_text = (
            f"✓ Le cours a été généré avec succès !\n\n"
            f"Statistiques :\n"
            f"- Nombre total de chapitres : {results['course_structure'].get('total_chapters', 0)}\n"
            f"- Nombre total de sources : {results['final_source_count']}\n"
            f"- Sources ajoutées : {results['sources_added']}\n\n"
            f"Téléchargement : {download_link}\n\n"
        )

        final_payload = {
            "id": message_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": request.model,
            "choices": [{
                "index": 0,
                "delta": {"content": final_text},
                "finish_reason": "stop"
            }]
        }

        yield f"data: {json.dumps(final_payload)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        heartbeat_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )



@app.get("/course/download/{filename:path}")
async def course_download(filename: str):
    file_path = os.path.normpath(filename)
    print(file_path)
    if not file_path.startswith(settings.DOWNLOAD_ALLOWED_BASE_PATH):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/octet-stream"
    if file_path.endswith('.docx'):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif file_path.endswith('.txt') or file_path.endswith('.log'):
        media_type = "text/plain"
    elif file_path.endswith('.md'):
        media_type = "text/markdown"
    elif file_path.endswith('.json'):
        media_type = "application/json"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=os.path.basename(file_path)
    )

# ==========================================================
# MAIN
# ==========================================================

@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "RAG & Course Generation Server",
        "version": "1.0.0",
        "endpoints": {
            "rag": "/rag",
            "course": "/course"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print(f"""
    ╔════════════════════════════════════════════════════════════════════╗
    ║             RAG & Course Generation Server                         ║
    ║                                                                    ║
    ║  RAG Endpoints:           /rag/*                                   ║
    ║  Course Endpoints:        /course/*                                ║
    ║                                                                    ║
    ║  Interactive docs: {settings.SERVER_BASE_URL}/docs              ║
    ╚════════════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host=settings.SERVER_HOST, port=settings.SERVER_PORT, log_level=settings.LOG_LEVEL)
