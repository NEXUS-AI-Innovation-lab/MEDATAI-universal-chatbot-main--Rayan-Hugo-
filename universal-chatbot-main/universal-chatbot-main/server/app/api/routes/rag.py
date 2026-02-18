"""
RAG endpoints router
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from datetime import datetime
import uuid

from app.models.schemas import ChatRequest
from app.core.auth import get_current_user
from app.services.rag_service import stream_rag_response
from rag_engine.rag import query_rag
from app.core.settings import settings

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.get("/api/models")
async def rag_models(current_user: dict = Depends(get_current_user)):
    """List available RAG collections as models"""
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
async def rag_chat(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    RAG chat completion endpoint

    Supports both streaming and non-streaming responses
    """
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    collection_name = request.model
    if collection_name not in settings.COLLECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection '{collection_name}'. Available: {list(settings.COLLECTIONS.keys())}"
        )

    question = user_messages[-1].content
    top_k = request.top_k or settings.RAG_DEFAULT_TOP_K

    if request.stream:
        return StreamingResponse(
            stream_rag_response(question, top_k, request.model, collection_name=collection_name),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        answer_with_links, used_sources = query_rag(question, collection_name=collection_name, top_k=top_k)
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
