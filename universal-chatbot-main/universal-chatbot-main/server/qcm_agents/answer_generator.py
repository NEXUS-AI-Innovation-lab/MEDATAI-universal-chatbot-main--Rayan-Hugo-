"""
Agent de Génération des Réponses et Choix (Phase 2)

Pour chaque question, génère:
- La réponse correcte à partir du contexte RAG
- Les mauvais choix selon le niveau de difficulté
- La référence au texte source
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict

# Note: sys.path manipulation needed for flat project structure
sys.path.insert(0, str(Path(__file__).parent.parent))
from course_build_agents.utils import context_from_query, call_llm, parse_llm_json_response, add_citation_links
from qcm_agents.prompts import get_answer_generator_system_prompt, get_answer_generator_user_prompt


class AnswerGeneratorAgent:
    """
    Agent 3: Générateur de Réponses et Choix (Phase 2)

    Pour chaque question:
    1. Lance une requête RAG ciblée avec la question
    2. Récupère les chunks pertinents
    3. Identifie la bonne réponse à partir du contexte
    4. Génère les mauvais choix selon la difficulté:
       - Facile: clairement incorrects, faciles à éliminer
       - Moyen: un plausible, un clairement faux
       - Difficile: les deux très plausibles, difficiles à distinguer
    5. Extrait le texte source utilisé pour la réponse
    """

    DIFFICULTY_LABELS = {
        "easy": "Facile",
        "medium": "Moyen",
        "hard": "Difficile"
    }

    def __init__(self, answer_top_k: int = 5, collection_name: str = None):
        """
        Initialise le générateur de réponses.

        Args:
            answer_top_k: Nombre de chunks à récupérer par question
            collection_name: Nom de la collection à utiliser pour les requêtes RAG
        """
        self.answer_top_k = answer_top_k
        self.collection_name = collection_name

    def generate_answers(
        self,
        questions: List[str],
        difficulty: str,
        topic: str
    ) -> List[Dict]:
        """
        Génère les réponses et choix pour toutes les questions.

        Args:
            questions: Liste des questions de la Phase 1
            difficulty: "easy" | "medium" | "hard"
            topic: Sujet original (pour le contexte)

        Returns:
            Liste d'éléments QCM, chacun contenant:
            {
                "question": str,
                "right_choice": str,
                "wrong_choice_1": str,
                "wrong_choice_2": str,
                "source_text": str,
                "source_url": str
            }
        """
        diff_label = self.DIFFICULTY_LABELS.get(difficulty, difficulty)

        print(f"\n{'='*60}")
        print(f"PHASE 2: Génération des Réponses et Choix")
        print(f"{'='*60}")
        print(f"Traitement de {len(questions)} questions...")
        print(f"Difficulté: {diff_label}")

        qcm_items = []

        for i, question in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] Traitement: {question[:50]}...")

            qcm_item = self._generate_answer_for_question(
                question=question,
                difficulty=difficulty,
                topic=topic,
                question_number=i
            )

            if qcm_item:
                qcm_items.append(qcm_item)
                print(f"   Correct: {qcm_item['right_choice'][:40]}...")
            else:
                print(f"   Échec de génération, question ignorée...")

        print(f"\n{'='*60}")
        print(f"{len(qcm_items)} éléments QCM générés avec succès")
        print(f"{'='*60}")

        return qcm_items

    def _generate_answer_for_question(
        self,
        question: str,
        difficulty: str,
        topic: str,
        question_number: int
    ) -> Dict:
        """Génère la réponse et les choix pour une question."""

        # Étape 1: Récupérer le contexte ciblé pour cette question
        knowledge_context, sources = context_from_query(question, collection_name=self.collection_name, top_k=self.answer_top_k)

        if not sources:
            print(f"   Aucune source trouvée pour cette question")
            return None

        # Étape 2: Générer la réponse et les choix avec le LLM
        return self._generate_qcm_item(
            question=question,
            difficulty=difficulty,
            topic=topic,
            knowledge_context=knowledge_context,
            sources=sources
        )

    def _generate_qcm_item(
        self,
        question: str,
        difficulty: str,
        topic: str,
        knowledge_context: str,
        sources: List[Dict]
    ) -> Dict:
        """Utilise le LLM pour générer l'élément QCM complet."""
        # Use centralized prompts from prompts.py
        system_prompt = get_answer_generator_system_prompt(topic, difficulty)
        user_prompt = get_answer_generator_user_prompt(question, difficulty, knowledge_context)

        response = call_llm(system_prompt, user_prompt)

        # Parse JSON response with automatic cleanup and repair
        result = parse_llm_json_response(
            response,
            expected_schema='{"right_choice": "...", "wrong_choice_1": "...", "wrong_choice_2": "...", "source_text": "..."}',
            fallback=None,
            context="answer generation"
        )

        if not result:
            return None

        # Validate required fields
        required = ["right_choice", "wrong_choice_1", "wrong_choice_2"]
        if not all(k in result for k in required):
            print(f"   [answer generation] Missing required fields: {required}")
            return None

        # Get URL and full chunk from first source
        source_url = sources[0].get('url', '') if sources else ''
        source_title = sources[0].get('title', '') if sources else ''
        # Use full chunk from source instead of LLM-extracted text
        full_chunk_text = sources[0].get('chunk_text', result.get("source_text", "")) if sources else result.get("source_text", "")

        return {
            "question": question,
            "right_choice": result["right_choice"],
            "wrong_choice_1": result["wrong_choice_1"],
            "wrong_choice_2": result["wrong_choice_2"],
            "source_text": full_chunk_text,
            "source_title": source_title,
            "source_url": source_url,
            "sources": sources  # Keep all sources for citations
        }


def format_qcm_markdown(qcm_items: List[Dict], topic: str, difficulty: str) -> str:
    """
    Formate les éléments QCM en markdown pour l'affichage.

    Args:
        qcm_items: Liste des dictionnaires d'éléments QCM
        topic: Sujet original
        difficulty: Niveau de difficulté

    Returns:
        Chaîne markdown formatée
    """
    import random

    difficulty_labels = {
        "easy": "Facile",
        "medium": "Moyen",
        "hard": "Difficile"
    }
    diff_label = difficulty_labels.get(difficulty, difficulty)

    lines = [
        f"# QCM: {topic}",
        f"**Difficulté:** {diff_label}",
        f"**Nombre de questions:** {len(qcm_items)}",
        "",
        "---",
        ""
    ]

    # Collecter toutes les sources utilisées pour la section finale
    all_sources = []
    source_counter = 1
    url_to_citation = {}  # Pour éviter les doublons de sources

    for i, item in enumerate(qcm_items, 1):
        # Mélanger les choix pour l'affichage (mais marquer le correct)
        choices = [
            ("A", item["right_choice"], True),
            ("B", item["wrong_choice_1"], False),
            ("C", item["wrong_choice_2"], False)
        ]
        random.shuffle(choices)

        # Trouver la lettre correcte après le mélange
        correct_letter = next(c[0] for c in choices if c[2])

        lines.append(f"## Question {i}")
        lines.append(f"**{item['question']}**")
        lines.append("")

        for letter, choice, is_correct in choices:
            lines.append(f"- **{letter}.** {choice}")

        lines.append("")
        lines.append(f"<details><summary>Voir la réponse</summary>")
        lines.append(f"")
        lines.append(f"**Réponse correcte: {correct_letter}**")

        # Afficher le chunk complet de la source
        if item.get("source_text"):
            lines.append(f"")
            lines.append(f"**Extrait source:**")
            lines.append(f"")
            lines.append(f"> {item['source_text']}")

        # Ajouter la citation style RAG [N](url)
        source_url = item.get("source_url", "")
        source_title = item.get("source_title", "Document")
        if source_url:
            if source_url not in url_to_citation:
                url_to_citation[source_url] = source_counter
                all_sources.append({
                    'number': source_counter,
                    'title': source_title,
                    'url': source_url
                })
                source_counter += 1

            citation_num = url_to_citation[source_url]
            lines.append(f"")
            lines.append(f"Source: [{citation_num}]({source_url})")

        lines.append(f"</details>")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Ajouter la section des sources à la fin (style RAG)
    if all_sources:
        lines.append("")
        lines.append("## Sources")
        lines.append("")
        for src in all_sources:
            lines.append(f"- [{src['number']}] [{src['title']}]({src['url']})")
        lines.append("")

    return "\n".join(lines)


def format_qcm_json(qcm_items: List[Dict], topic: str, difficulty: str) -> Dict:
    """
    Formate les éléments QCM en JSON structuré pour l'export.

    Args:
        qcm_items: Liste des dictionnaires d'éléments QCM
        topic: Sujet original
        difficulty: Niveau de difficulté

    Returns:
        Dictionnaire structuré prêt pour la sérialisation JSON
    """
    import random

    difficulty_labels = {
        "easy": "Facile",
        "medium": "Moyen",
        "hard": "Difficile"
    }

    formatted_items = []

    for i, item in enumerate(qcm_items, 1):
        # Créer le tableau de choix avec la bonne réponse marquée
        choices = [
            {"text": item["right_choice"], "is_correct": True},
            {"text": item["wrong_choice_1"], "is_correct": False},
            {"text": item["wrong_choice_2"], "is_correct": False}
        ]
        random.shuffle(choices)

        formatted_items.append({
            "number": i,
            "question": item["question"],
            "choices": choices,
            "source": {
                "text": item.get("source_text", ""),
                "title": item.get("source_title", ""),
                "url": item.get("source_url", "")
            }
        })

    return {
        "topic": topic,
        "difficulty": difficulty,
        "difficulty_label": difficulty_labels.get(difficulty, difficulty),
        "total_questions": len(formatted_items),
        "questions": formatted_items
    }


def format_qcm_downloadable(qcm_items: List[Dict], topic: str, difficulty: str) -> Dict:
    """
    Formate les éléments QCM en JSON téléchargeable.

    Structure: {question, ans_list} où la première réponse est toujours correcte.

    Args:
        qcm_items: Liste des dictionnaires d'éléments QCM
        topic: Sujet original
        difficulty: Niveau de difficulté

    Returns:
        Dictionnaire avec structure simplifiée pour téléchargement
    """
    difficulty_labels = {
        "easy": "Facile",
        "medium": "Moyen",
        "hard": "Difficile"
    }

    questions_list = []

    for item in qcm_items:
        # ans_list avec la bonne réponse TOUJOURS en premier
        ans_list = [
            item["right_choice"],      # Index 0 = toujours correct
            item["wrong_choice_1"],    # Index 1 = incorrect
            item["wrong_choice_2"]     # Index 2 = incorrect
        ]

        questions_list.append({
            "question": item["question"],
            "ans_list": ans_list,
            "source": {
                "text": item.get("source_text", ""),
                "title": item.get("source_title", ""),
                "url": item.get("source_url", "")
            }
        })

    return {
        "metadata": {
            "topic": topic,
            "difficulty": difficulty,
            "difficulty_label": difficulty_labels.get(difficulty, difficulty),
            "total_questions": len(questions_list),
            "note": "Dans ans_list, la premiere reponse (index 0) est toujours la bonne reponse"
        },
        "questions": questions_list
    }
