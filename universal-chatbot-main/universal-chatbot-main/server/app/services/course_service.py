"""
Course generation service
"""
import os
import json
import asyncio
import uuid
from datetime import datetime
from course_build_agents.orchestrator_with_logging import stream_course_generation_progress
from app.core.settings import settings
from app.services.streaming_utils import async_stream_wrapper_with_heartbeat


async def stream_course_generation(subject: str, model: str = "course-generator", collection_name: str = None):
    """
    Stream course generation with progress as reasoning_content

    Args:
        subject: Course subject/topic
        model: Model identifier
        collection_name: Name of the collection to use for RAG queries

    Yields:
        str: Server-sent events formatted response chunks
    """
    message_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_timestamp = int(datetime.now().timestamp())

    config = {
        'retriever_top_k': settings.course.retriever_top_k,
        'enhancer_iterations': settings.course.enhancer_iterations,
        'enhancer_top_k': settings.course.enhancer_top_k,
        'collection_name': collection_name,
    }

    try:
        loop = asyncio.get_event_loop()

        # Track last heartbeat time
        last_heartbeat = asyncio.get_event_loop().time()
        heartbeat_interval = 10  # seconds

        # Run the streaming generator in executor and process updates
        # (bridges sync generator to async iteration with heartbeat support)
        async for update in async_stream_wrapper_with_heartbeat(
            loop, stream_course_generation_progress, subject, config,
            heartbeat_interval=heartbeat_interval
        ):
            if update['type'] == 'heartbeat':
                # Send heartbeat (empty content to maintain connection)
                heartbeat_chunk = {
                    "id": message_id,
                    "object": "chat.completion.chunk",
                    "created": created_timestamp,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(heartbeat_chunk)}\n\n"

            elif update['type'] == 'progress':
                # Send progress as reasoning_content (appears in thinking box)
                progress_chunk = {
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
                yield f"data: {json.dumps(progress_chunk)}\n\n"

            elif update['type'] == 'complete':
                # Get final results
                results = update['results']
                course_markdown = results.get('course_markdown', '')

                # Add statistics summary at the end
                summary = (
                    f"\n\n---\n\n"
                    f"**Statistiques de génération :**\n"
                    f"- Nombre total de chapitres : {results['course_structure'].get('total_chapters', 0)}\n"
                    f"- Nombre total de sources : {results['final_source_count']}\n"
                    f"- Sources ajoutées : {results['sources_added']}\n"
                )

                final_content = course_markdown + summary

                # Stream the markdown content in chunks (like RAG does)
                chunk_size = settings.RAG_CHUNK_SIZE
                for i in range(0, len(final_content), chunk_size):
                    chunk = final_content[i:i+chunk_size]
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

        # Send finish signal
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
            "id": message_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n\nErreur: {str(e)}"},
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


# Note: async_stream_wrapper_with_heartbeat is now imported from streaming_utils.py
# This removes ~70 lines of duplicated code that was also in qcm_service.py
