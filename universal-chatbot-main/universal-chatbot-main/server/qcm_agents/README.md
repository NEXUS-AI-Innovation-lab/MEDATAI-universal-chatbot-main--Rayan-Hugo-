# QCM Generator - Documentation

## Vue d'ensemble

Le generateur de QCM (Questions a Choix Multiples) est un systeme multi-agents qui cree automatiquement des quiz a partir d'une base de connaissances RAG (Retrieval-Augmented Generation).

## Architecture

Le systeme est compose de 4 composants principaux:

```
┌─────────────────────────────────────────────────────────────┐
│                     QCM Orchestrator                        │
│   Coordonne le processus complet de generation              │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ State Manager │    │   Question    │    │    Answer     │
│    Agent      │    │   Generator   │    │   Generator   │
│               │    │   (Phase 1)   │    │   (Phase 2)   │
└───────────────┘    └───────────────┘    └───────────────┘
```

### 1. State Manager Agent (`state_manager.py`)

Gere la conversation avec l'utilisateur pour collecter les parametres:
- **topic**: Sujet des questions
- **difficulty**: Niveau de difficulte (easy/medium/hard)
- **number**: Nombre de questions a generer

L'agent guide l'utilisateur etape par etape et demande confirmation avant de lancer la generation.

### 2. Question Generator Agent (`question_generator.py`) - Phase 1

1. Lance une requete RAG avec le sujet pour recuperer un large contexte (15 chunks par defaut)
2. Analyse le contexte pour identifier les concepts cles
3. Genere N questions pedagogiques adaptees au niveau de difficulte
4. Retourne les questions avec le contexte source

### 3. Answer Generator Agent (`answer_generator.py`) - Phase 2

Pour chaque question generee en Phase 1:

1. Lance une requete RAG ciblee avec la question (5 chunks par defaut)
2. Identifie la bonne reponse a partir du contexte
3. Genere 2 mauvais choix selon le niveau de difficulte:
   - **Facile**: Mauvais choix clairement incorrects
   - **Moyen**: Un choix plausible + un clairement faux
   - **Difficile**: Deux choix tres plausibles
4. Extrait le texte source complet pour la citation

### 4. Orchestrator (`orchestrator.py`)

Coordonne l'ensemble du processus:
- Gere le flux de conversation
- Lance les phases de generation
- Formate les sorties (Markdown, JSON)
- Upload le JSON telechargeable au fileserver

## Flux de Generation

```
Utilisateur: "Genere un QCM sur Python"
                    │
                    ▼
┌─────────────────────────────────────┐
│ State Manager: Demande difficulte   │
└─────────────────────────────────────┘
                    │
                    ▼
Utilisateur: "Moyen, 5 questions"
                    │
                    ▼
┌─────────────────────────────────────┐
│ State Manager: Confirme parametres  │
└─────────────────────────────────────┘
                    │
                    ▼
Utilisateur: "Oui"
                    │
                    ▼
┌─────────────────────────────────────┐
│ PHASE 1: Requete RAG large          │
│ → Recupere 15 chunks sur "Python"   │
│ → Genere 5 questions                │
└─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────┐
│ PHASE 2: Pour chaque question       │
│ → Requete RAG ciblee (5 chunks)     │
│ → Genere reponse + mauvais choix    │
│ → Stocke chunk source complet       │
└─────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────┐
│ Formatage et Upload                 │
│ → Markdown avec sources             │
│ → JSON telechargeable               │
│ → Upload au fileserver              │
└─────────────────────────────────────┘
```

## Format de Sortie

### Markdown

Le QCM est formate en Markdown avec:
- Questions numerotees avec choix melanges (A, B, C)
- Section repliable "Voir la reponse" contenant:
  - La lettre de la bonne reponse
  - L'extrait source complet (pas tronque)
  - Lien vers la source au format `[N](url)`
- Section "Sources" a la fin avec toutes les references

### JSON Telechargeable

Structure `{question, ans_list}`:

```json
{
  "metadata": {
    "topic": "Python",
    "difficulty": "medium",
    "difficulty_label": "Moyen",
    "total_questions": 5,
    "note": "Dans ans_list, la premiere reponse (index 0) est toujours la bonne reponse"
  },
  "questions": [
    {
      "question": "Quelle est la syntaxe pour definir une fonction en Python?",
      "ans_list": [
        "def nom_fonction():",     // Index 0 = TOUJOURS correct
        "function nom_fonction()", // Index 1 = incorrect
        "func nom_fonction:"       // Index 2 = incorrect
      ],
      "source": {
        "text": "En Python, les fonctions sont definies avec le mot-cle def...",
        "title": "Guide Python",
        "url": "http://..."
      }
    }
  ]
}
```

## Systeme de Citations

Le generateur utilise le meme systeme de citation que le RAG:

1. Les chunks sont recuperes avec des IDs sequentiels
2. Les sources sont referencees avec `[N](url)` dans le Markdown
3. Les URLs de PDF sont converties en liens fileserver si disponibles
4. Une section "Sources" liste toutes les references utilisees

## Configuration

Configuration via `app/core/settings.py` (environnement ou `.env`):

| Variable | Acces Settings | Defaut | Description |
|----------|---------------|--------|-------------|
| `QCM_RETRIEVER_TOP_K` | `settings.qcm.retriever_top_k` | 15 | Chunks pour Phase 1 |
| `QCM_ANSWER_TOP_K` | `settings.qcm.answer_top_k` | 5 | Chunks par question Phase 2 |
| `FILESERVER_BASE` | `settings.fileserver.base_url` | http://localhost:7700 | URL du serveur de fichiers |

Exemple d'acces:
```python
from app.core.settings import settings

top_k = settings.qcm.retriever_top_k  # 15
fileserver = settings.fileserver.base_url  # http://localhost:7700
```

## Endpoints API

### Mode Conversationnel

```
POST /api/qcm/chat
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "Genere un QCM sur Python"}
  ],
  "model": "qcm-generator"
}
```

### Mode Direct

```
POST /api/qcm/generate
Content-Type: application/json

{
  "topic": "Python",
  "difficulty": "medium",
  "number": 5
}
```

## Fichiers

| Fichier | Description |
|---------|-------------|
| `orchestrator.py` | Point d'entree, coordonne la generation |
| `state_manager.py` | Gestion de conversation et parametres |
| `question_generator.py` | Phase 1 - Generation des questions |
| `answer_generator.py` | Phase 2 - Generation des reponses + formatage |

## Exemple d'Utilisation Programmatique

```python
from qcm_agents.orchestrator import QCMOrchestrator

# Initialiser
orchestrator = QCMOrchestrator({
    'retriever_top_k': 15,
    'answer_top_k': 5
})

# Generer
results = orchestrator.generate_qcm(
    topic="Les bases de Python",
    difficulty="medium",
    number=5
)

# Acceder aux resultats
print(results['markdown'])  # Affichage Markdown
print(results['json'])      # Structure JSON
```
