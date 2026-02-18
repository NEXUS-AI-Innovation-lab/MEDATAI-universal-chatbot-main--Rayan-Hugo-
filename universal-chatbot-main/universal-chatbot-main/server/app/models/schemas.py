"""
Pydantic models and schemas for API requests/responses
"""
from pydantic import BaseModel
from typing import Optional, List


class ChatMessage(BaseModel):
    """Chat message model"""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat completion request model"""
    model: str = "rag-hybrid"
    messages: List[ChatMessage]
    stream: bool = True
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    top_k: Optional[int] = 5
