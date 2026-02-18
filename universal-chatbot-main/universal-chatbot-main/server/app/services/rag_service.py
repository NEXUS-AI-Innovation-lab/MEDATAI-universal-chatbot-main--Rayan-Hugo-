"""
RAG service for streaming responses
"""
import json
import asyncio
import uuid
from datetime import datetime
from rag_engine.rag import stream_rag_with_thinking
from app.core.settings import settings
from app.services.streaming_utils import async_stream_wrapper


async def stream_rag_response(question: str, top_k: int = 5, model: str = "rag-hybrid", collection_name: str = "btp"):
    """
    Stream RAG response with thinking from Ollama, then corrected final response

    Args:
        question: User question
        top_k: Number of top results to retrieve
        model: Model identifier
        collection_name: Collection name to query

    Yields:
        str: Server-sent events formatted response chunks
    """
    try:
        message_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created_timestamp = int(datetime.now().timestamp())

        loop = asyncio.get_event_loop()

        # Use the async wrapper to stream in real-time
        # (bridges sync generator to async iteration)
        async for update in async_stream_wrapper(loop, stream_rag_with_thinking, question, collection_name, top_k):
            if update['type'] == 'thinking':
                # Stream Ollama response as reasoning_content (thinking box)
                thinking_chunk = {
                    "id": message_id,
                    "object": "chat.completion.chunk",
                    "created": created_timestamp,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "reasoning_content": update['content']
                        },
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(thinking_chunk)}\n\n"

            elif update['type'] == 'final':
                # Send final corrected response with sources
                answer_with_links = update['content']
                used_sources = update['sources']

                if used_sources:
                    sources_text = "\n\n**Sources:**\n"
                    for idx, source in enumerate(used_sources, 1):
                        sources_text += f"{idx}. [{source['title']}]({source['url']})\n"
                    answer_with_links += sources_text

                # Send complete final response
                final_content_chunk = {
                    "id": message_id,
                    "object": "chat.completion.chunk",
                    "created": created_timestamp,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": answer_with_links},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(final_content_chunk)}\n\n"

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


# Note: async_stream_wrapper is now imported from streaming_utils.py
# This removes ~50 lines of duplicated code that was also in course_service.py and qcm_service.py
