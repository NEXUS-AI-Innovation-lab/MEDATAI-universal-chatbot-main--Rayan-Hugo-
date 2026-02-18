"""
Routes API de Génération de QCM

Fournit les endpoints pour:
- Génération de QCM conversationnelle avec gestion d'état
- Génération directe de QCM quand les paramètres sont connus
- Liste des modèles disponibles
"""

import json
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse

from app.models.schemas import ChatRequest
from app.core.auth import get_current_user
from app.services.qcm_service import (
    stream_qcm_response,
    stream_qcm_direct_generation
)
from app.core.settings import settings

router = APIRouter()


@router.get("/api/models")
async def list_qcm_models(current_user: dict = Depends(get_current_user)):
    """Liste les collections disponibles pour la génération de QCM."""
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
async def qcm_chat_completions(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint de génération de QCM.

    The request.model must be a valid collection name (e.g., "btp", "medatai").

    Le système utilise un mode conversationnel qui va:
    - Demander les paramètres manquants (sujet, difficulté, nombre)
    - Afficher une confirmation avant de générer
    - Générer le QCM après confirmation
    """
    # Convertir les messages en format dict
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in request.messages
    ]

    if not messages:
        raise HTTPException(status_code=400, detail="Aucun message trouvé")

    # Extract and validate collection_name from request.model
    collection_name = request.model
    if not collection_name or collection_name not in settings.COLLECTIONS:
        available = list(settings.COLLECTIONS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection '{collection_name}'. Available collections: {available}"
        )

    # Mode conversationnel - passer l'HISTORIQUE COMPLET des messages
    return StreamingResponse(
        stream_qcm_response(
            messages=messages,
            model=collection_name,
            collection_name=collection_name
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def _parse_direct_command(message: str) -> Optional[dict]:
    """
    Parse une commande de génération directe.

    Formats attendus:
    - "Génère 5 questions moyennes sur Python"
    - "Crée 10 QCM difficiles sur le machine learning"
    - "5 questions faciles sur les bases de données"
    """
    import re

    message_lower = message.lower()

    # Essayer d'extraire le nombre
    number_match = re.search(r'(\d+)\s*(?:questions?|qcm)?', message_lower)
    number = int(number_match.group(1)) if number_match else None

    # Essayer d'extraire la difficulté
    difficulty = None
    if any(w in message_lower for w in ['facile', 'simple', 'easy']):
        difficulty = 'easy'
    elif any(w in message_lower for w in ['moyen', 'moyenne', 'medium', 'intermédiaire']):
        difficulty = 'medium'
    elif any(w in message_lower for w in ['difficile', 'hard', 'dur', 'avancé']):
        difficulty = 'hard'

    # Essayer d'extraire le sujet (après "sur", "about", "concernant", etc.)
    topic_match = re.search(
        r'(?:sur|about|on|concernant|à propos de?)\s+(.+?)(?:\s*$|\s*[,.])',
        message,
        re.IGNORECASE
    )
    topic = topic_match.group(1).strip() if topic_match else None

    # Si on n'a pas trouvé le sujet avec les patterns, essayer autrement
    if not topic:
        # Retirer les mots-clés connus et voir ce qui reste
        cleaned = re.sub(
            r'(génère|générer|crée|créer|faire|qcm|questions?|facile|moyen|moyenne|difficile|simple|dur|avancé|\d+)',
            '',
            message_lower
        ).strip()
        if len(cleaned) > 3:
            topic = cleaned

    # Retourner les params si on a les trois
    if topic and difficulty and number:
        return {
            "topic": topic,
            "difficulty": difficulty,
            # Question limit: 1-50
            # - Minimum 1: at least one question needed
            # - Maximum 50: ~4 minutes generation time at 50 questions
            #   (each question requires RAG query + LLM calls for answers)
            "number": min(max(number, 1), 50)
        }

    return None


# Note: _help_response function was removed as dead code (never called)
