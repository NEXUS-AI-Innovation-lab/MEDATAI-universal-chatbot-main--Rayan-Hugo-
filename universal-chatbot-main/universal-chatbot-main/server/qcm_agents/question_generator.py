"""
Agent de Génération de Questions (Phase 1)

Génère N questions à partir d'un large contexte de la base de connaissances.
Ne génère PAS les réponses ni les choix - c'est la Phase 2.
"""

import json
import re
import sys
from pathlib import Path
from typing import List

# Note: sys.path manipulation needed for flat project structure
# This allows importing from sibling directories without package installation
sys.path.insert(0, str(Path(__file__).parent.parent))
from course_build_agents.utils import context_from_query, call_llm, parse_llm_json_response
from qcm_agents.prompts import get_question_generator_system_prompt, get_question_generator_user_prompt


class QuestionGeneratorAgent:
    """
    Agent 2: Générateur de Questions (Phase 1)

    Processus:
    1. Reçoit les paramètres confirmés (topic, difficulty, number)
    2. Lance UNE requête RAG avec un grand top_k pour un contexte large
    3. Génère exactement N questions pertinentes au sujet
    4. Retourne uniquement les questions (pas de réponses, pas de choix, pas de sources)
    """

    DIFFICULTY_LABELS = {
        "easy": "Facile",
        "medium": "Moyen",
        "hard": "Difficile"
    }

    def __init__(self, retriever_top_k: int = 15, collection_name: str = None):
        """
        Initialise le générateur de questions.

        Args:
            retriever_top_k: Nombre de chunks à récupérer pour le contexte large
            collection_name: Nom de la collection à utiliser pour les requêtes RAG
        """
        self.retriever_top_k = retriever_top_k
        self.collection_name = collection_name

    def generate_questions(self, topic: str, difficulty: str, number: int) -> dict:
        """
        Génère N questions sur le sujet.

        Args:
            topic: Sujet des questions
            difficulty: "easy" | "medium" | "hard"
            number: Nombre de questions à générer

        Returns:
            dict: {
                "questions": List[str],
                "knowledge_context": str,
                "sources": List[dict]
            }
        """
        diff_label = self.DIFFICULTY_LABELS.get(difficulty, difficulty)

        print(f"\n{'='*60}")
        print(f"PHASE 1: Génération des Questions")
        print(f"{'='*60}")
        print(f"Sujet: {topic}")
        print(f"Difficulté: {diff_label}")
        print(f"Nombre de questions: {number}")
        print(f"Récupération des {self.retriever_top_k} meilleurs chunks...")

        # Étape 1: Récupérer le contexte large
        knowledge_context, sources = context_from_query(topic, collection_name=self.collection_name, top_k=self.retriever_top_k)

        print(f"Sources récupérées: {len(sources)}")
        for i, src in enumerate(sources[:5], 1):
            print(f"  [{i}] {src.get('title', 'Sans titre')[:50]}...")
        if len(sources) > 5:
            print(f"  ... et {len(sources) - 5} autres")

        # Étape 2: Générer les questions avec le LLM
        print(f"\nGénération de {number} questions...")

        questions = self._generate_questions_from_context(
            topic=topic,
            difficulty=difficulty,
            number=number,
            knowledge_context=knowledge_context
        )

        print(f"\n{len(questions)} questions générées:")
        for i, q in enumerate(questions, 1):
            print(f"  Q{i}: {q[:60]}{'...' if len(q) > 60 else ''}")

        return {
            "questions": questions,
            "knowledge_context": knowledge_context,
            "sources": sources
        }

    def _generate_questions_from_context(
        self,
        topic: str,
        difficulty: str,
        number: int,
        knowledge_context: str
    ) -> List[str]:
        """Génère les questions avec le LLM à partir du contexte récupéré."""
        # Use centralized prompts from prompts.py
        system_prompt = get_question_generator_system_prompt(topic, number, difficulty)
        user_prompt = get_question_generator_user_prompt(topic, number, difficulty, knowledge_context)

        response = call_llm(system_prompt, user_prompt)

        # Parse JSON response with automatic cleanup and repair
        result = parse_llm_json_response(
            response,
            expected_schema='{"questions": ["question1", "question2", ...]}',
            fallback=None,
            context="question generation"
        )

        if result and "questions" in result:
            questions = result["questions"]

            # Validate count
            if len(questions) != number:
                print(f"   Attention: {len(questions)} questions reçues, {number} attendues")
                if len(questions) > number:
                    questions = questions[:number]

            return questions

        # Fallback: extract questions from raw text
        return self._extract_questions_fallback(response, number)

    def _extract_questions_fallback(self, text: str, number: int) -> List[str]:
        """Extraction de secours si le parsing JSON échoue."""
        print("   Utilisation de l'extraction de secours...")

        lines = text.split('\n')
        questions = []

        for line in lines:
            line = line.strip()
            # Retirer la numérotation
            line = re.sub(r'^[\d]+[\.\)\-]\s*', '', line)
            line = re.sub(r'^["\']', '', line)
            line = re.sub(r'["\']$', '', line)
            line = line.strip()

            # Vérifier si ça ressemble à une question
            if line and (line.endswith('?') or line.endswith('?,')):
                line = line.rstrip(',')
                questions.append(line)

                if len(questions) >= number:
                    break

        return questions
