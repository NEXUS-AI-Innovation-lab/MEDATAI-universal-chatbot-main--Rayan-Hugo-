"""
Agent de Gestion d'État pour la Génération de QCM

Utilise le LLM pour analyser intelligemment la conversation et déterminer:
- Les paramètres extraits (topic, difficulty, number)
- Si l'utilisateur a confirmé ou non
- Quelle action prendre ensuite
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict

# Note: sys.path manipulation needed for flat project structure
sys.path.insert(0, str(Path(__file__).parent.parent))
from course_build_agents.utils import call_llm, parse_llm_json_response
from qcm_agents.prompts import STATE_MANAGER_SYSTEM_PROMPT, get_state_manager_user_prompt


class StateManagerAgent:
    """
    Agent 1: Gestionnaire d'État Intelligent

    Utilise le LLM pour analyser l'HISTORIQUE COMPLET de la conversation
    et déterminer l'état actuel ainsi que l'action à prendre.
    """

    VALID_DIFFICULTIES = ["easy", "medium", "hard"]
    DIFFICULTY_LABELS = {
        "easy": "Facile",
        "medium": "Moyen",
        "hard": "Difficile"
    }

    def __init__(self):
        self.state = {
            "topic": None,
            "difficulty": None,
            "number": None,
            "confirmed": False
        }

    def process_conversation(self, messages: List[Dict]) -> dict:
        """
        Analyse l'HISTORIQUE COMPLET de la conversation avec le LLM.

        Args:
            messages: Liste complète des messages [{"role": "user"|"assistant", "content": str}, ...]

        Returns:
            dict: {
                "state": état actuel,
                "ready": bool - True si prêt à générer,
                "response": str - Message à renvoyer à l'utilisateur,
                "action": str - "ask_params" | "confirm" | "proceed"
            }
        """
        if not messages:
            return {
                "state": self.state.copy(),
                "ready": False,
                "response": self._generate_welcome_message(),
                "action": "ask_params"
            }

        # Utiliser le LLM pour analyser la conversation complète
        analysis = self._analyze_conversation_with_llm(messages)

        # Mettre à jour l'état
        self.state["topic"] = analysis.get("topic")
        self.state["difficulty"] = analysis.get("difficulty")
        self.state["number"] = analysis.get("number")
        self.state["confirmed"] = analysis.get("confirmed", False)

        # Déterminer l'action basée sur l'analyse du LLM
        if self.state["confirmed"] and self._is_complete():
            # Utilisateur a confirmé et tous les paramètres sont présents
            return {
                "state": self.state.copy(),
                "ready": True,
                "response": None,
                "action": "proceed"
            }
        elif self._is_complete():
            # Tous les paramètres sont là mais pas encore confirmé
            response = self._generate_confirmation_message()
            return {
                "state": self.state.copy(),
                "ready": False,
                "response": response,
                "action": "confirm"
            }
        else:
            # Paramètres manquants
            response = self._generate_missing_params_message()
            return {
                "state": self.state.copy(),
                "ready": False,
                "response": response,
                "action": "ask_params"
            }

    def _analyze_conversation_with_llm(self, messages: List[Dict]) -> dict:
        """
        Utilise le LLM pour analyser toute la conversation et extraire:
        - Les paramètres (topic, difficulty, number)
        - Si l'utilisateur a confirmé la configuration
        """
        # Format conversation for LLM
        conversation_text = ""
        for msg in messages:
            role = "Utilisateur" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")
            conversation_text += f"{role}: {content}\n\n"

        # Use centralized prompts from prompts.py
        system_prompt = STATE_MANAGER_SYSTEM_PROMPT
        user_prompt = get_state_manager_user_prompt(conversation_text)

        response = call_llm(system_prompt, user_prompt)

        # Default empty state
        default_state = {"topic": None, "difficulty": None, "number": None, "confirmed": False}

        # Parse JSON response with automatic cleanup and repair
        analysis = parse_llm_json_response(
            response,
            expected_schema='{"topic": "...", "difficulty": "...", "number": N, "confirmed": true/false}',
            fallback=default_state,
            context="StateManager"
        )

        if not analysis or analysis == default_state:
            return default_state

        # Validate and normalize the parsed data
        result = {
            "topic": None,
            "difficulty": None,
            "number": None,
            "confirmed": False
        }

        if analysis.get("topic"):
            result["topic"] = str(analysis["topic"]).strip()

        if analysis.get("difficulty"):
            diff = str(analysis["difficulty"]).lower().strip()
            diff_map = {
                "facile": "easy", "easy": "easy", "simple": "easy",
                "moyen": "medium", "medium": "medium", "moyenne": "medium", "intermédiaire": "medium",
                "difficile": "hard", "hard": "hard", "dur": "hard", "avancé": "hard"
            }
            result["difficulty"] = diff_map.get(diff, diff if diff in ["easy", "medium", "hard"] else None)

        if analysis.get("number"):
            try:
                num = int(analysis["number"])
                if 1 <= num <= 50:
                    result["number"] = num
            except (ValueError, TypeError):
                pass

        result["confirmed"] = bool(analysis.get("confirmed", False))

        return result

    def _is_complete(self) -> bool:
        """Vérifie si tous les paramètres requis sont présents."""
        return all([
            self.state["topic"] is not None,
            self.state["difficulty"] is not None,
            self.state["number"] is not None
        ])

    def _generate_welcome_message(self) -> str:
        """Message d'accueil initial."""
        return (
            "Bienvenue dans le générateur de QCM!\n\n"
            "Pour créer vos questions, j'ai besoin de:\n"
            "- **Le sujet** des questions\n"
            "- **La difficulté** (facile, moyen, difficile)\n"
            "- **Le nombre** de questions\n\n"
            "Dites-moi ce que vous souhaitez!"
        )

    def _generate_confirmation_message(self) -> str:
        """Message de demande de confirmation."""
        diff_label = self.DIFFICULTY_LABELS.get(self.state["difficulty"], self.state["difficulty"])

        return (
            f"**Configuration du QCM:**\n"
            f"- **Sujet:** {self.state['topic']}\n"
            f"- **Difficulté:** {diff_label}\n"
            f"- **Nombre de questions:** {self.state['number']}\n\n"
            f"Est-ce correct? Répondez **oui** pour confirmer ou indiquez vos modifications."
        )

    def _generate_missing_params_message(self) -> str:
        """Message demandant les paramètres manquants."""
        missing = []

        if self.state["topic"] is None:
            missing.append("le **sujet** des questions")
        if self.state["difficulty"] is None:
            missing.append("la **difficulté** (facile, moyen, difficile)")
        if self.state["number"] is None:
            missing.append("le **nombre** de questions")

        # Afficher ce qu'on a déjà
        current = []
        if self.state["topic"]:
            current.append(f"Sujet: {self.state['topic']}")
        if self.state["difficulty"]:
            current.append(f"Difficulté: {self.DIFFICULTY_LABELS.get(self.state['difficulty'])}")
        if self.state["number"]:
            current.append(f"Questions: {self.state['number']}")

        response = ""
        if current:
            response += f"Bien noté! Configuration actuelle: {', '.join(current)}\n\n"

        response += f"Il me manque: {', '.join(missing)}"

        return response

    def get_confirmed_params(self) -> dict:
        """Récupère les paramètres confirmés pour la génération."""
        if not self.state["confirmed"]:
            raise ValueError("Paramètres non encore confirmés")

        return {
            "topic": self.state["topic"],
            "difficulty": self.state["difficulty"],
            "number": self.state["number"]
        }
