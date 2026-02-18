"""
Couche Service QCM

Gère les réponses streaming pour l'endpoint de génération de QCM.
Fait le pont entre l'orchestrateur QCM et les réponses SSE FastAPI.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional

import sys
from pathlib import Path
# sys.path manipulation for flat project structure
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from qcm_agents.orchestrator import handle_qcm_conversation, stream_qcm_generation
from qcm_agents.state_manager import StateManagerAgent
from app.core.settings import settings
from app.services.streaming_utils import async_stream_wrapper_with_heartbeat


async def stream_qcm_response(
    messages: List[Dict],
    model: str = "qcm-generator",
    collection_name: str = None
) -> AsyncGenerator[str, None]:
    """
    Stream la réponse de conversation QCM en SSE.

    Gère les deux phases:
    1. Phase de gestion d'état (demande de paramètres)
    2. Phase de génération (création du QCM)

    Args:
        messages: HISTORIQUE COMPLET des messages [{"role": "user"|"assistant", "content": str}, ...]
        model: Nom du modèle pour la réponse
        collection_name: Nom de la collection à utiliser pour les requêtes RAG

    Yields:
        str: Chunks formatés en SSE
    """
    message_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_timestamp = int(datetime.now().timestamp())

    config = {
        'retriever_top_k': settings.qcm.retriever_top_k,
        'answer_top_k': settings.qcm.answer_top_k,
        'collection_name': collection_name,
    }

    def make_chunk(delta: Dict, finish_reason: str = None) -> Dict:
        return {
            "id": message_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason
            }]
        }

    try:
        loop = asyncio.get_event_loop()

        # Stream la gestion de conversation avec l'historique COMPLET
        async for update in async_stream_wrapper_with_heartbeat(
            loop,
            handle_qcm_conversation,
            messages,  # Passer l'historique COMPLET
            config,
            heartbeat_interval=10
        ):
            if update['type'] == 'heartbeat':
                # Envoyer un heartbeat vide
                heartbeat = make_chunk({"role": "assistant"})
                yield f"data: {json.dumps(heartbeat)}\n\n"

            elif update['type'] == 'state':
                # Mise à jour d'état - pourrait être stocké côté serveur si nécessaire
                pass

            elif update['type'] == 'response':
                # Réponse texte - envoyer comme content
                content = update['content']
                if content:
                    # Stream caractère par caractère pour un affichage fluide
                    chunk_size = settings.RAG_CHUNK_SIZE
                    for i in range(0, len(content), chunk_size):
                        text_chunk = content[i:i + chunk_size]
                        chunk = make_chunk({"content": text_chunk})
                        yield f"data: {json.dumps(chunk)}\n\n"
                        await asyncio.sleep(settings.RAG_CHUNK_DELAY)

            elif update['type'] == 'progress':
                # Mise à jour de progression - envoyer comme reasoning_content (boîte de réflexion)
                progress = update['content']
                if progress:
                    chunk = make_chunk({
                        "role": "assistant",
                        "reasoning_content": progress
                    })
                    yield f"data: {json.dumps(chunk)}\n\n"

            elif update['type'] == 'complete':
                # Génération terminée - envoyer le markdown final
                results = update['results']
                markdown = results.get('markdown', '')
                downloadable_json = results.get('downloadable_json')
                download_url = results.get('download_url')

                if markdown:
                    # Stream le contenu markdown
                    chunk_size = settings.RAG_CHUNK_SIZE
                    for i in range(0, len(markdown), chunk_size):
                        text_chunk = markdown[i:i + chunk_size]
                        chunk = make_chunk({"content": text_chunk})
                        yield f"data: {json.dumps(chunk)}\n\n"
                        await asyncio.sleep(settings.RAG_CHUNK_DELAY)

                # Envoyer le JSON téléchargeable comme metadata
                if downloadable_json:
                    qcm_data_chunk = {
                        "id": message_id,
                        "object": "chat.completion.chunk",
                        "created": created_timestamp,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": None
                        }],
                        "qcm_download": {
                            "json_data": downloadable_json,
                            "download_url": download_url
                        }
                    }
                    yield f"data: {json.dumps(qcm_data_chunk, ensure_ascii=False)}\n\n"

        # Envoyer le signal de fin
        finish_chunk = make_chunk({}, "stop")
        yield f"data: {json.dumps(finish_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        # Envoyer un message d'erreur
        error_chunk = make_chunk({"content": f"\n\nErreur: {str(e)}"})
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"


async def stream_qcm_direct_generation(
    topic: str,
    difficulty: str,
    number: int,
    model: str = "qcm-generator",
    collection_name: str = None
) -> AsyncGenerator[str, None]:
    """
    Stream la génération de QCM directement (sans gestion d'état).

    Utiliser quand tous les paramètres sont déjà connus.

    Args:
        topic: Sujet des questions
        difficulty: "easy" | "medium" | "hard"
        number: Nombre de questions
        model: Nom du modèle pour la réponse
        collection_name: Nom de la collection à utiliser pour les requêtes RAG

    Yields:
        str: Chunks formatés en SSE
    """
    message_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_timestamp = int(datetime.now().timestamp())

    config = {
        'retriever_top_k': settings.qcm.retriever_top_k,
        'answer_top_k': settings.qcm.answer_top_k,
        'collection_name': collection_name,
    }

    def make_chunk(delta: Dict, finish_reason: str = None) -> Dict:
        return {
            "id": message_id,
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason
            }]
        }

    try:
        loop = asyncio.get_event_loop()

        async for update in async_stream_wrapper_with_heartbeat(
            loop,
            stream_qcm_generation,
            topic,
            difficulty,
            number,
            config,
            heartbeat_interval=10
        ):
            if update['type'] == 'heartbeat':
                heartbeat = make_chunk({"role": "assistant"})
                yield f"data: {json.dumps(heartbeat)}\n\n"

            elif update['type'] == 'progress':
                progress = update['content']
                if progress:
                    chunk = make_chunk({
                        "role": "assistant",
                        "reasoning_content": progress
                    })
                    yield f"data: {json.dumps(chunk)}\n\n"

            elif update['type'] == 'complete':
                results = update['results']
                markdown = results.get('markdown', '')
                downloadable_json = results.get('downloadable_json')
                download_url = results.get('download_url')

                if markdown:
                    chunk_size = settings.RAG_CHUNK_SIZE
                    for i in range(0, len(markdown), chunk_size):
                        text_chunk = markdown[i:i + chunk_size]
                        chunk = make_chunk({"content": text_chunk})
                        yield f"data: {json.dumps(chunk)}\n\n"
                        await asyncio.sleep(settings.RAG_CHUNK_DELAY)

                # Envoyer le JSON téléchargeable comme metadata
                if downloadable_json:
                    qcm_data_chunk = {
                        "id": message_id,
                        "object": "chat.completion.chunk",
                        "created": created_timestamp,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": None
                        }],
                        "qcm_download": {
                            "json_data": downloadable_json,
                            "download_url": download_url
                        }
                    }
                    yield f"data: {json.dumps(qcm_data_chunk, ensure_ascii=False)}\n\n"

        finish_chunk = make_chunk({}, "stop")
        yield f"data: {json.dumps(finish_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        error_chunk = make_chunk({"content": f"\n\nErreur: {str(e)}"})
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"
