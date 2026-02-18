"""
QCM Orchestrator - Multi-Agent Quiz Generation System
======================================================

This module coordinates the complete QCM (Multiple Choice Questions) generation
process using a multi-agent architecture with streaming support.

Architecture Overview
---------------------

    ┌─────────────────────────────────────────────────────────────────┐
    │                     QCM ORCHESTRATOR                            │
    │  Coordinates agents, manages state, handles streaming output    │
    └─────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
    ┌───────────────┐      ┌───────────────┐      ┌───────────────┐
    │ StateManager  │      │  Question     │      │   Answer      │
    │    Agent      │      │  Generator    │      │  Generator    │
    │               │      │   (Phase 1)   │      │   (Phase 2)   │
    │ - Extracts    │      │               │      │               │
    │   params from │      │ - Retrieves   │      │ - Per-question│
    │   conversation│      │   broad       │      │   RAG query   │
    │ - Tracks      │      │   context     │      │ - Generates   │
    │   state       │      │ - Generates N │      │   correct ans │
    │ - Confirms    │      │   questions   │      │ - Creates     │
    │   before gen  │      │               │      │   distractors │
    └───────────────┘      └───────────────┘      └───────────────┘

State Flow
----------
The orchestrator manages conversation state through these transitions:

    INITIAL ──────────────────────────────────────────────────────────┐
        │                                                              │
        │ User sends first message                                     │
        ▼                                                              │
    ┌─────────┐                                                        │
    │ PARTIAL │◄──────────────────────────────────────────┐            │
    │         │  User provides some params                 │            │
    │ Missing │  (topic, difficulty, or number)           │            │
    │ params  │                                            │            │
    └────┬────┘                                            │            │
         │                                                 │            │
         │ All params provided                             │            │
         ▼                                                 │            │
    ┌──────────┐                                           │            │
    │ COMPLETE │  All params present, awaiting confirm     │            │
    │          │                                           │            │
    │ topic    │  User says "no" or modifies ──────────────┘            │
    │ diff     │                                                        │
    │ number   │                                                        │
    └────┬─────┘                                                        │
         │                                                              │
         │ User confirms ("oui", "ok", "lance", etc.)                   │
         ▼                                                              │
    ┌───────────┐                                                       │
    │ CONFIRMED │  Ready to generate                                    │
    │           │                                                       │
    │ Start     ├────► Phase 1 (Questions) ────► Phase 2 (Answers)     │
    │ generation│                                                       │
    └───────────┘                                                       │

Message Types Yielded
---------------------
The streaming generator yields these message types:

    {"type": "state", "state": {...}}
        Current state for client-side persistence

    {"type": "response", "content": "..."}
        Text response to show the user (prompts, confirmations)

    {"type": "progress", "content": "..."}
        Generation progress updates (shown in thinking/reasoning box)

    {"type": "complete", "results": {...}}
        Final QCM results with markdown, JSON, and download URL

Entry Points
------------
    - handle_qcm_conversation(): Main entry for conversational mode
    - stream_qcm_generation(): Direct generation when params are known
    - QCMOrchestrator: Class for synchronous (non-streaming) generation
"""

import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Generator, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.settings import settings
from .state_manager import StateManagerAgent
from .question_generator import QuestionGeneratorAgent
from .answer_generator import AnswerGeneratorAgent, format_qcm_markdown, format_qcm_json, format_qcm_downloadable

# For uploading QCM JSON to fileserver
import hashlib
import json
import requests

# Fileserver URLs from centralized settings
FILESERVER_BASE = settings.fileserver.base_url
FILESERVER_PUBLIC_URL = settings.fileserver.public_base_url


def upload_qcm_to_fileserver(qcm_data: dict, topic: str) -> dict:
    """
    Upload QCM JSON to the fileserver for download.

    Args:
        qcm_data: The downloadable QCM data structure
        topic: Topic of the QCM (used in filename)

    Returns:
        dict: Upload result with hash_code and download_url, or error
    """
    print(f"[UPLOAD] FILESERVER_BASE = {FILESERVER_BASE}")

    try:
        # Generate a hash from the content
        json_content = json.dumps(qcm_data, ensure_ascii=False, indent=2)
        content_hash = hashlib.sha256(json_content.encode('utf-8')).hexdigest()[:16]

        # Prepare the upload request
        upload_url = f"{FILESERVER_BASE}/upload"
        print(f"[UPLOAD] Uploading to: {upload_url}")
        print(f"[UPLOAD] Hash: {content_hash}")

        # Create a file-like object for the upload
        files = {
            'file': (f"qcm_{topic[:20]}.json", json_content.encode('utf-8'), 'application/json')
        }
        data = {
            'custom_hash': content_hash,
            'extension': 'json'
        }

        response = requests.post(upload_url, files=files, data=data, timeout=30)
        print(f"[UPLOAD] Response status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            # Use public URL for browser downloads
            download_url = f"{FILESERVER_PUBLIC_URL}{result.get('download_url')}"
            print(f"[UPLOAD] Success! Download URL: {download_url}")
            return {
                "success": True,
                "hash_code": result.get("hash_code"),
                "download_url": download_url,
                "filename": result.get("saved_as")
            }
        else:
            error_msg = f"Upload failed: {response.status_code} - {response.text}"
            print(f"[UPLOAD] ERROR: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

    except requests.exceptions.RequestException as e:
        error_msg = f"Connection error to {FILESERVER_BASE}: {str(e)}"
        print(f"[UPLOAD] ERROR: {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"Upload error: {str(e)}"
        print(f"[UPLOAD] ERROR: {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }


class StreamingPrintCapture:
    """Capture les print statements dans un buffer pour le streaming."""

    def __init__(self):
        self.original_stdout = sys.stdout
        self.buffer = []

    def write(self, text):
        self.original_stdout.write(text)
        self.buffer.append(text)

    def flush(self):
        self.original_stdout.flush()

    def get_and_clear(self):
        content = ''.join(self.buffer)
        self.buffer = []
        return content


class QCMOrchestrator:
    """
    Orchestrateur principal pour la génération de QCM.

    Gère le cycle de vie complet:
    - Gestion de l'état de conversation
    - Génération des questions (Phase 1)
    - Génération des réponses (Phase 2)
    - Formatage des sorties
    """

    def __init__(self, config: Dict = None):
        """
        Initialise l'orchestrateur.

        Args:
            config: Dictionnaire de configuration avec clés optionnelles:
                - retriever_top_k: Chunks pour le contexte large (défaut: 15)
                - answer_top_k: Chunks par question (défaut: 5)
                - output_dir: Répertoire pour sauvegarder les sorties
                - collection_name: Nom de la collection à utiliser pour les requêtes RAG
        """
        config = config or {}

        # Extract collection_name from config
        collection_name = config.get('collection_name')

        self.state_manager = StateManagerAgent()
        self.question_generator = QuestionGeneratorAgent(
            retriever_top_k=config.get('retriever_top_k', 15),
            collection_name=collection_name
        )
        self.answer_generator = AnswerGeneratorAgent(
            answer_top_k=config.get('answer_top_k', 5),
            collection_name=collection_name
        )

        self.output_dir = config.get('output_dir', './qcm_outputs')
        os.makedirs(self.output_dir, exist_ok=True)

        # Stocker les résultats
        self.results = {}

    def process_conversation(self, messages: List[Dict]) -> Dict:
        """
        Traite l'HISTORIQUE COMPLET de la conversation.

        Args:
            messages: Liste complète des messages [{"role": "user"|"assistant", "content": str}, ...]

        Returns:
            dict: {
                "response": str - Message à retourner à l'utilisateur,
                "ready": bool - True si prêt à générer,
                "state": dict - État actuel
            }
        """
        result = self.state_manager.process_conversation(messages)

        return {
            "response": result["response"],
            "ready": result["ready"],
            "state": result["state"],
            "action": result["action"]
        }

    def generate_qcm(self, topic: str, difficulty: str, number: int) -> Dict:
        """
        Génère le QCM de manière synchrone (sans streaming).

        Args:
            topic: Sujet des questions
            difficulty: "easy" | "medium" | "hard"
            number: Nombre de questions

        Returns:
            dict: Résultats complets incluant éléments QCM, markdown et JSON
        """
        difficulty_labels = {"easy": "Facile", "medium": "Moyen", "hard": "Difficile"}
        diff_label = difficulty_labels.get(difficulty, difficulty)

        print(f"\n{'='*80}")
        print(f"SYSTÈME DE GÉNÉRATION DE QCM")
        print(f"{'='*80}")
        print(f"Sujet: {topic}")
        print(f"Difficulté: {diff_label}")
        print(f"Questions: {number}")
        print(f"Démarré: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        start_time = datetime.now()

        # Phase 1: Générer les questions
        phase1_result = self.question_generator.generate_questions(
            topic=topic,
            difficulty=difficulty,
            number=number
        )

        self.results['questions'] = phase1_result['questions']
        self.results['knowledge_context'] = phase1_result['knowledge_context']
        self.results['initial_sources'] = phase1_result['sources']

        # Phase 2: Générer les réponses pour chaque question
        qcm_items = self.answer_generator.generate_answers(
            questions=phase1_result['questions'],
            difficulty=difficulty,
            topic=topic
        )

        self.results['qcm_items'] = qcm_items

        # Formater les sorties
        markdown_content = format_qcm_markdown(qcm_items, topic, difficulty)
        json_content = format_qcm_json(qcm_items, topic, difficulty)

        self.results['markdown'] = markdown_content
        self.results['json'] = json_content

        # Calculer la durée
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n{'='*80}")
        print(f"GÉNÉRATION QCM TERMINÉE")
        print(f"{'='*80}")
        print(f"Durée: {duration:.2f} secondes")
        print(f"Questions générées: {len(phase1_result['questions'])}")
        print(f"Éléments QCM complétés: {len(qcm_items)}")
        print(f"{'='*80}")

        self.results['duration'] = duration
        self.results['topic'] = topic
        self.results['difficulty'] = difficulty

        return self.results

    def save_outputs(self, filename_prefix: str = None) -> Dict[str, str]:
        """
        Sauvegarde les sorties QCM dans des fichiers.

        Args:
            filename_prefix: Préfixe optionnel pour les noms de fichiers

        Returns:
            dict: Chemins vers les fichiers sauvegardés
        """
        if not self.results.get('qcm_items'):
            raise ValueError("Pas de résultats QCM à sauvegarder. Lancez generate_qcm d'abord.")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        prefix = filename_prefix or f"qcm_{self.results['topic'][:20]}_{timestamp}"
        prefix = prefix.replace(' ', '_').replace('/', '_')

        paths = {}

        # Sauvegarder le markdown
        md_path = os.path.join(self.output_dir, f"{prefix}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(self.results['markdown'])
        paths['markdown'] = md_path

        # Sauvegarder le JSON
        import json
        json_path = os.path.join(self.output_dir, f"{prefix}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.results['json'], f, indent=2, ensure_ascii=False)
        paths['json'] = json_path

        print(f"Sorties sauvegardées:")
        print(f"  Markdown: {md_path}")
        print(f"  JSON: {json_path}")

        return paths


def stream_qcm_generation(
    topic: str,
    difficulty: str,
    number: int,
    config: Dict = None
) -> Generator[Dict, None, None]:
    """
    Stream la génération de QCM avec mises à jour de progression.

    Yield des dictionnaires avec mises à jour de progression:
    - {"type": "progress", "content": str} - Messages de progression
    - {"type": "complete", "results": dict} - Résultats finaux

    Args:
        topic: Sujet des questions
        difficulty: "easy" | "medium" | "hard"
        number: Nombre de questions
        config: Configuration optionnelle

    Yields:
        dict: Mises à jour de progression et résultats finaux
    """
    capture = StreamingPrintCapture()
    old_stdout = sys.stdout
    sys.stdout = capture

    difficulty_labels = {"easy": "Facile", "medium": "Moyen", "hard": "Difficile"}
    diff_label = difficulty_labels.get(difficulty, difficulty)

    try:
        # En-tête
        print(f"\n{'='*60}")
        print(f"SYSTÈME DE GÉNÉRATION DE QCM")
        print(f"{'='*60}")
        print(f"Sujet: {topic}")
        print(f"Difficulté: {diff_label}")
        print(f"Questions: {number}")
        print(f"{'='*60}")

        header = capture.get_and_clear()
        if header:
            yield {"type": "progress", "content": header}

        # Initialiser l'orchestrateur
        config = config or {}
        orchestrator = QCMOrchestrator(config)

        start_time = datetime.now()

        # Phase 1: Générer les questions
        print(f"\n{'='*60}")
        print(f"PHASE 1: Génération des Questions")
        print(f"{'='*60}")

        phase1_header = capture.get_and_clear()
        if phase1_header:
            yield {"type": "progress", "content": phase1_header}

        phase1_result = orchestrator.question_generator.generate_questions(
            topic=topic,
            difficulty=difficulty,
            number=number
        )

        phase1_logs = capture.get_and_clear()
        if phase1_logs:
            yield {"type": "progress", "content": phase1_logs}

        # Phase 2: Générer les réponses
        print(f"\n{'='*60}")
        print(f"PHASE 2: Génération des Réponses et Choix")
        print(f"{'='*60}")
        print(f"Traitement de {len(phase1_result['questions'])} questions...")

        phase2_header = capture.get_and_clear()
        if phase2_header:
            yield {"type": "progress", "content": phase2_header}

        qcm_items = []
        questions = phase1_result['questions']

        for i, question in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] {question[:50]}...")

            qcm_item = orchestrator.answer_generator._generate_answer_for_question(
                question=question,
                difficulty=difficulty,
                topic=topic,
                question_number=i
            )

            if qcm_item:
                qcm_items.append(qcm_item)
                print(f"   Terminé")
            else:
                print(f"   Échec, question ignorée")

            # Yield la progression après chaque question
            question_progress = capture.get_and_clear()
            if question_progress:
                yield {"type": "progress", "content": question_progress}

        # Formater les sorties
        markdown_content = format_qcm_markdown(qcm_items, topic, difficulty)
        json_content = format_qcm_json(qcm_items, topic, difficulty)

        # Générer le JSON téléchargeable (première réponse = correcte)
        downloadable_json = format_qcm_downloadable(qcm_items, topic, difficulty)

        # Uploader le JSON au fileserver
        print(f"\nUpload du JSON téléchargeable...")
        upload_result = upload_qcm_to_fileserver(downloadable_json, topic)

        download_url = None
        if upload_result.get("success"):
            download_url = upload_result.get("download_url")
            print(f"   Upload réussi: {download_url}")
        else:
            print(f"   Erreur upload: {upload_result.get('error')}")

        # Résumé
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        print(f"\n{'='*60}")
        print(f"TERMINÉ")
        print(f"{'='*60}")
        print(f"Durée: {duration:.2f}s")
        print(f"Généré: {len(qcm_items)}/{number} questions")
        if download_url:
            print(f"Télécharger: {download_url}")
        print(f"{'='*60}")

        summary = capture.get_and_clear()
        if summary:
            yield {"type": "progress", "content": summary}

        # Ajouter le lien de téléchargement au markdown
        if download_url:
            markdown_content += f"\n\n---\n\n**[Télécharger le QCM (JSON)]({download_url})**\n"

        # Yield les résultats finaux
        yield {
            "type": "complete",
            "results": {
                "topic": topic,
                "difficulty": difficulty,
                "questions_requested": number,
                "questions_generated": len(qcm_items),
                "qcm_items": qcm_items,
                "markdown": markdown_content,
                "json": json_content,
                "downloadable_json": downloadable_json,
                "download_url": download_url,
                "duration": duration
            }
        }

    finally:
        sys.stdout = old_stdout


def handle_qcm_conversation(
    messages: List[Dict],
    config: Dict = None
) -> Generator[Dict, None, None]:
    """
    Gère un tour de conversation QCM avec streaming.

    C'est le point d'entrée principal pour l'endpoint QCM.
    Gère à la fois la phase de gestion d'état et la phase de génération.

    Args:
        messages: HISTORIQUE COMPLET des messages [{"role": "user"|"assistant", "content": str}, ...]
        config: Configuration optionnelle

    Yields:
        dict: Différents types de mises à jour:
            - {"type": "response", "content": str} - Réponse texte à l'utilisateur
            - {"type": "progress", "content": str} - Progression pendant la génération
            - {"type": "complete", "results": dict} - Résultats QCM finaux
            - {"type": "state", "state": dict} - État mis à jour à sauvegarder
    """
    config = config or {}

    # Initialiser le gestionnaire d'état
    state_manager = StateManagerAgent()

    # Traiter l'historique complet de la conversation
    result = state_manager.process_conversation(messages)

    # Yield l'état actuel pour sauvegarde
    yield {"type": "state", "state": result["state"]}

    if result["ready"]:
        # Paramètres confirmés - lancer la génération
        params = state_manager.get_confirmed_params()

        yield {"type": "response", "content": f"Lancement de la génération du QCM...\n\n"}

        # Stream la génération
        for update in stream_qcm_generation(
            topic=params["topic"],
            difficulty=params["difficulty"],
            number=params["number"],
            config=config
        ):
            yield update

    else:
        # Pas prêt - retourner la réponse demandant plus d'infos ou confirmation
        yield {"type": "response", "content": result["response"]}
