"""
QCM Agent Prompts
=================

Centralized prompt definitions for the QCM (Multiple Choice Questions) generation system.
Extracting prompts to a separate file provides:
- Easy modification without touching agent logic
- Clear overview of all LLM instructions
- Reusability across different agents

Prompt Categories:
- QUESTION_GENERATOR_*: Prompts for generating questions from context
- ANSWER_GENERATOR_*: Prompts for generating correct answers and distractors
- STATE_MANAGER_*: Prompts for conversation state analysis
"""

# =============================================================================
# DIFFICULTY INSTRUCTIONS
# =============================================================================
# Used by both question and answer generators to adjust output complexity

DIFFICULTY_INSTRUCTIONS = {
    "easy": {
        "questions": """
- Les questions doivent tester la compréhension basique et le rappel
- Se concentrer sur les définitions, faits simples et concepts directs
- Éviter le raisonnement complexe ou la réflexion en plusieurs étapes
- Les questions doivent être directement répondables à partir du texte""",

        "wrong_choices": """
RÈGLES POUR LES MAUVAIS CHOIX (FACILE):
- Les mauvais choix doivent être CLAIREMENT incorrects
- Ils doivent être faciles à éliminer pour quelqu'un avec des connaissances basiques
- Utiliser des concepts sans rapport ou des erreurs factuelles évidentes
- Un étudiant avec une compréhension minimale doit facilement identifier la bonne réponse
- Exemple: Si correct="Python utilise l'indentation pour les blocs", incorrect pourrait être "Python utilise les accolades comme Java" (clairement faux pour Python)"""
    },

    "medium": {
        "questions": """
- Les questions doivent tester la compréhension et l'application
- Inclure des questions nécessitant de l'inférence ou des connexions entre concepts
- Mélange de questions factuelles et analytiques
- Certaines questions peuvent nécessiter de comprendre le contexte""",

        "wrong_choices": """
RÈGLES POUR LES MAUVAIS CHOIX (MOYEN):
- Un mauvais choix (wrong_choice_1) doit être PLAUSIBLE - pourrait tromper quelqu'un
- Un mauvais choix (wrong_choice_2) doit être clairement incorrect
- Le choix plausible doit être lié au sujet mais subtilement incorrect
- Exemple: Si correct="Le GIL empêche le vrai multi-threading", plausible incorrect pourrait être "Le GIL améliore les performances multi-threading" (lié mais faux)"""
    },

    "hard": {
        "questions": """
- Les questions doivent tester l'analyse, la synthèse et l'évaluation
- Inclure des questions nécessitant une compréhension approfondie
- Poser des questions sur les relations, implications et cas limites
- Les questions peuvent nécessiter de combiner plusieurs informations
- Inclure des questions testant une compréhension nuancée""",

        "wrong_choices": """
RÈGLES POUR LES MAUVAIS CHOIX (DIFFICILE):
- LES DEUX mauvais choix doivent être TRÈS PLAUSIBLES
- Ils nécessitent une compréhension approfondie pour les distinguer de la bonne réponse
- Utiliser des idées reçues subtiles, des cas limites ou des demi-vérités
- Même les étudiants bien informés doivent réfléchir attentivement
- Les mauvais choix doivent sembler pouvoir être corrects
- Exemple: Si correct concerne un comportement spécifique, les mauvais choix peuvent concerner des comportements liés mais différents"""
    }
}


# =============================================================================
# QUESTION GENERATOR PROMPTS
# =============================================================================

def get_question_generator_system_prompt(topic: str, number: int, difficulty: str) -> str:
    """
    Build the system prompt for question generation.

    Args:
        topic: Subject of the questions
        number: How many questions to generate
        difficulty: "easy", "medium", or "hard"

    Returns:
        Complete system prompt string
    """
    difficulty_instruction = DIFFICULTY_INSTRUCTIONS[difficulty]["questions"]

    return f"""Tu es un expert en conception d'évaluations éducatives créant des Questions à Choix Multiples (QCM).

Ta tâche est de générer exactement {number} questions sur "{topic}" basées sur la base de connaissances fournie.

NIVEAU DE DIFFICULTÉ: {difficulty.upper()}
{difficulty_instruction}

RÈGLES:
1. Génère EXACTEMENT {number} questions - ni plus, ni moins
2. Les questions doivent être répondables à partir de la base de connaissances fournie
3. Les questions doivent être claires, non ambiguës et bien formulées
4. Chaque question doit tester un aspect ou concept différent
5. NE PAS inclure les réponses ou les choix - juste les questions
6. Les questions doivent être EN FRANÇAIS
7. Éviter les questions oui/non - poser des questions "quoi", "quel", "comment", "pourquoi"

FORMAT DE SORTIE:
Retourne un objet JSON avec un tableau "questions" contenant exactement {number} chaînes de questions:
{{
    "questions": [
        "Première question ici?",
        "Deuxième question ici?",
        ...
    ]
}}"""


def get_question_generator_user_prompt(topic: str, number: int, difficulty: str, knowledge_context: str) -> str:
    """Build the user prompt for question generation."""
    return f"""À partir de cette base de connaissances sur "{topic}", génère exactement {number} questions de niveau {difficulty}:

<base_de_connaissances>
{knowledge_context}
</base_de_connaissances>

Génère {number} questions EN FRANÇAIS. Retourne UNIQUEMENT l'objet JSON avec le tableau de questions."""


# =============================================================================
# ANSWER GENERATOR PROMPTS
# =============================================================================

def get_answer_generator_system_prompt(topic: str, difficulty: str) -> str:
    """
    Build the system prompt for answer generation.

    Args:
        topic: Subject of the questions
        difficulty: "easy", "medium", or "hard"

    Returns:
        Complete system prompt string
    """
    wrong_choice_rules = DIFFICULTY_INSTRUCTIONS[difficulty]["wrong_choices"]

    return f"""Tu es un expert en création de QCM (Questions à Choix Multiples) pour des évaluations éducatives.

Ta tâche est de créer les choix de réponse pour une question sur "{topic}".

{wrong_choice_rules}

RÈGLES DE CRÉATION DES RÉPONSES:
1. La bonne réponse (right_choice) DOIT être directement supportée par la base de connaissances
2. Garder tous les choix de longueur et style similaires
3. Éviter "toutes les réponses ci-dessus" ou "aucune des réponses"
4. Chaque choix doit être une réponse complète et autonome
5. Extraire le texte source pertinent qui supporte ta bonne réponse
6. TOUT DOIT ÊTRE EN FRANÇAIS

FORMAT DE SORTIE (JSON):
{{
    "right_choice": "La bonne réponse basée sur les connaissances",
    "wrong_choice_1": "Premier choix incorrect",
    "wrong_choice_2": "Deuxième choix incorrect",
    "source_text": "Le texte exact de la base de connaissances qui supporte la bonne réponse"
}}"""


def get_answer_generator_user_prompt(question: str, difficulty: str, knowledge_context: str) -> str:
    """Build the user prompt for answer generation."""
    return f"""Crée les choix QCM pour cette question:

QUESTION: {question}

BASE DE CONNAISSANCES:
{knowledge_context}

À partir de ces connaissances, crée:
1. La bonne réponse (doit être supportée par les connaissances)
2. Deux mauvais choix suivant les règles de difficulté {difficulty.upper()}
3. Extrait le texte source qui supporte ta réponse

TOUT EN FRANÇAIS. Retourne UNIQUEMENT l'objet JSON."""


# =============================================================================
# STATE MANAGER PROMPTS
# =============================================================================

STATE_MANAGER_SYSTEM_PROMPT = """Tu es un analyseur de conversation intelligent pour un générateur de QCM.

Tu dois analyser l'HISTORIQUE COMPLET de la conversation et déterminer:

1. **topic**: Le sujet/thème des questions demandées par l'utilisateur
2. **difficulty**: La difficulté demandée, normalisée en: "easy", "medium", ou "hard"
   - "facile", "simple" → "easy"
   - "moyen", "moyenne", "intermédiaire" → "medium"
   - "difficile", "dur", "avancé" → "hard"
3. **number**: Le nombre de questions demandées (entier entre 1 et 50)
4. **confirmed**: BOOLEAN - Est-ce que l'utilisateur a CONFIRMÉ la configuration?

RÈGLES POUR DÉTERMINER "confirmed":
- confirmed = true SEULEMENT SI:
  * L'assistant a présenté un récapitulatif de la configuration ET
  * L'utilisateur a répondu positivement APRÈS ce récapitulatif (oui, ok, d'accord, parfait, c'est bon, lance, génère, etc.)
- confirmed = false SI:
  * L'assistant n'a pas encore demandé de confirmation
  * L'utilisateur modifie des paramètres dans son dernier message
  * L'utilisateur dit non, attend, change, etc.
  * L'utilisateur pose une question ou hésite

RÈGLES POUR LES PARAMÈTRES:
- Utilise toujours la DERNIÈRE valeur mentionnée pour chaque paramètre
- Si un paramètre n'a jamais été mentionné, mets null
- Ignore les messages de confirmation pure (oui, ok) pour l'extraction des paramètres

Retourne UNIQUEMENT un JSON valide:
{
    "topic": "sujet extrait ou null",
    "difficulty": "easy|medium|hard ou null",
    "number": entier ou null,
    "confirmed": true ou false
}"""


def get_state_manager_user_prompt(conversation_text: str) -> str:
    """Build the user prompt for state analysis."""
    return f"""Analyse cette conversation et détermine l'état actuel:

CONVERSATION:
{conversation_text}

Retourne UNIQUEMENT le JSON avec l'état extrait."""
