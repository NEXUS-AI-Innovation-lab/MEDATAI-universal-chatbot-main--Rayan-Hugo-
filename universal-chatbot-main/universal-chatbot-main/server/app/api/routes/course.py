"""
Course generation endpoints router
"""
import os
import uuid
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, FileResponse
from datetime import datetime

from app.models.schemas import ChatRequest
from app.core.auth import get_current_user
from app.services.course_service import stream_course_generation
from app.core.settings import settings

router = APIRouter(prefix="/course", tags=["Course Generation"])


@router.get("/api/models")
async def course_models(current_user: dict = Depends(get_current_user)):
    """Liste les collections disponibles pour la génération de cours."""
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
async def course_chat(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Course generation endpoint

    Generates a complete course based on the subject provided.
    The request.model must be a valid collection name (e.g., "btp", "medatai").
    """
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

    # Extract and validate collection_name from request.model
    collection_name = request.model
    if not collection_name or collection_name not in settings.COLLECTIONS:
        available = list(settings.COLLECTIONS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection '{collection_name}'. Available collections: {available}"
        )

    return StreamingResponse(
        stream_course_generation(subject, collection_name, collection_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/download/{filename:path}")
async def course_download(filename: str):
    """
    Download generated course files

    Args:
        filename: Path to the file to download

    Returns:
        FileResponse: The requested file
    """
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
