# Architecture de Streaming en Temps Réel

Ce document explique comment fonctionne le système de streaming en temps réel pour la génération de cours, incluant la capture des outputs, le système d'événements SSE, et les heartbeats.

---

## Vue d'ensemble : Streaming en Temps Réel avec Thinking Box

L'objectif est de streamer la progression de la génération de cours vers le client en temps réel, en affichant les mises à jour dans une "thinking box" tout en maintenant la connexion avec des heartbeats.

---

## 1. Système de Capture des Prints (`orchestrator_with_logging.py`)

### Le Problème
Les agents (retriever, enhancer, generator) utilisent des instructions `print()` pour logger leur progression. Par défaut, ces messages vont vers stdout et disparaissent.

### La Solution : `StreamingPrintCapture`

```python
class StreamingPrintCapture:
    def __init__(self):
        self.original_stdout = sys.stdout
        self.buffer = []

    def write(self, text):
        self.original_stdout.write(text)  # Continue d'afficher en console
        self.buffer.append(text)          # Sauvegarde aussi le texte

    def get_and_clear(self):
        content = ''.join(self.buffer)
        self.buffer = []
        return content
```

**Comment ça fonctionne :**
1. Remplace `sys.stdout` par notre objet personnalisé
2. Intercepte tous les appels `print()`
3. Stocke les messages dans un buffer
4. Récupère et vide le buffer périodiquement

---

## 2. Générateur de Streaming de Progression (`orchestrator_with_logging.py`)

### `stream_course_generation_progress()`

```python
def stream_course_generation_progress(subject, config=None):
    capture = StreamingPrintCapture()
    sys.stdout = capture  # Redirige tous les prints

    try:
        # Phase 1
        print("PHASE 1: RÉCUPÉRATION DES CONNAISSANCES")
        yield {'type': 'progress', 'content': capture.get_and_clear()}

        retriever.retrieve_knowledge(subject)  # Ceci print des messages
        yield {'type': 'progress', 'content': capture.get_and_clear()}

        # Phase 2, 3, etc...

        # Résultat final
        yield {'type': 'complete', 'results': {...}}
    finally:
        sys.stdout = old_stdout  # Restaure stdout normal
```

**Comment ça fonctionne :**
1. **Capture les prints** : Redirige stdout vers notre capture personnalisée
2. **Effectue le travail** : Appelle les méthodes des agents (qui printent la progression)
3. **Yield du texte capturé** : Récupère tous les prints depuis le dernier yield, les envoie
4. **Répète** : Après chaque étape majeure, yield les logs accumulés

**Les yields ressemblent à :**
- `{'type': 'progress', 'content': '📚 Agent 1 : Collecte...\n'}`
- `{'type': 'complete', 'results': {...}}`

---

## 3. Wrapper de Streaming Asynchrone (`course_service.py`)

### Le Problème
Le générateur s'exécute de manière synchrone (bloquante), mais FastAPI est asynchrone. Nous devons :
- Exécuter le générateur sans bloquer l'event loop
- Streamer les résultats en temps réel (ne pas attendre la fin)
- Envoyer des heartbeats toutes les 10s

### La Solution : Threading + Queue

```python
async def async_stream_wrapper_with_heartbeat(loop, generator_func, *args, heartbeat_interval=10):
    result_queue = queue.Queue()

    def run_generator():
        # S'exécute dans un thread en arrière-plan
        for item in generator_func(*actual_args):
            result_queue.put(('item', item))  # Met dans la queue immédiatement
        result_queue.put(('done', None))

    thread = threading.Thread(target=run_generator, daemon=True)
    thread.start()  # Démarre le travail en arrière-plan

    last_heartbeat = time.time()

    while True:
        # Vérifie si 10 secondes se sont écoulées → envoie heartbeat
        if time.time() - last_heartbeat >= 10:
            yield {'type': 'heartbeat'}
            last_heartbeat = time.time()

        # Vérifie la queue pour de nouveaux items (non-bloquant)
        result = await loop.run_in_executor(None, get_with_timeout)

        if result:
            yield result  # Yield progress ou complete
        else:
            await asyncio.sleep(0.01)  # Rien dans la queue, attend un peu
```

**Comment ça fonctionne :**

1. **Thread en Arrière-plan** :
   - Exécute `stream_course_generation_progress()`
   - Ne bloque pas l'event loop asynchrone

2. **Communication par Queue** :
   - Le générateur met des items : `queue.put(('item', {...}))`
   - Le wrapper récupère des items : `queue.get(timeout=0.1)`
   - Transfert en temps réel entre le thread et l'async

3. **Timer de Heartbeat** :
   - Suit l'heure du dernier heartbeat
   - Toutes les 10s, yield `{'type': 'heartbeat'}`
   - Maintient la connexion active

4. **Polling Asynchrone** :
   - Vérifie la queue toutes les 0.1s
   - Si vide, dort 0.01s, vérifie à nouveau
   - Si a un item, le yield immédiatement

---

## 4. Couche Service (`course_service.py`)

### `stream_course_generation()`

```python
async def stream_course_generation(subject, model):
    async for update in async_stream_wrapper_with_heartbeat(...):
        if update['type'] == 'heartbeat':
            # Envoie chunk vide (maintient la connexion)
            yield f"data: {json.dumps({...delta: {}...})}\n\n"

        elif update['type'] == 'progress':
            # Envoie comme reasoning_content (thinking box)
            yield f"data: {json.dumps({...delta: {"reasoning_content": update['content']}...})}\n\n"

        elif update['type'] == 'complete':
            # Envoie le cours markdown final
            yield f"data: {json.dumps({...delta: {"content": markdown}...})}\n\n"
```

**Comment ça fonctionne :**
1. Reçoit les mises à jour du wrapper
2. Convertit en format Server-Sent Events (SSE)
3. Envoie le JSON approprié selon le type

---

## 5. Format SSE & Affichage Client

### Différents Types de Delta :

**Heartbeat :**
```json
{
  "delta": {},
  "finish_reason": null
}
```
- Maintient la connexion active
- N'affiche rien

**Progression (Thinking Box) :**
```json
{
  "delta": {
    "role": "assistant",
    "reasoning_content": "📚 Agent 1 : Collecte...\n"
  },
  "finish_reason": null
}
```
- `reasoning_content` → apparaît dans la thinking box grise
- L'utilisateur voit la progression en temps réel

**Réponse Finale :**
```json
{
  "delta": {"content": "# Titre du Cours\n..."},
  "finish_reason": null
}
```
- `content` régulier → apparaît dans la réponse principale
- Le markdown du cours réel

---

## Diagramme de Flux Complet

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Client envoie une requête                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. FastAPI: stream_course_generation()                      │
│    - Crée le wrapper async avec heartbeat                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Thread en arrière-plan démarre:                          │
│    - stream_course_generation_progress()                    │
│    - Redirige stdout vers capture                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Agent 1: KnowledgeRetrieverAgent                         │
│    print("📚 Agent 1 : Collecte...")  ←── Capturé           │
│    print("Requête 1/10...")           ←── Capturé           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Le générateur yield:                                     │
│    yield {'type': 'progress', 'content': texte_capturé}     │
│           ↓ Mis dans la queue                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Le wrapper async poll la queue:                          │
│    - Récupère l'item de la queue                            │
│    - Yield vers la couche service                           │
│    - (Envoie aussi heartbeat toutes les 10s)                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Service convertit en SSE:                                │
│    yield "data: {...reasoning_content...}\n\n"              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Client reçoit:                                           │
│    - Affiche dans thinking box: "📚 Agent 1 : Collecte..."  │
│    - Toutes les 10s: heartbeat maintient la connexion       │
└─────────────────────────────────────────────────────────────┘
                            ↓
                     (Répète 4-8 pour chaque phase)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Le générateur yield final:                               │
│    yield {'type': 'complete', 'results': {...}}             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 10. Service envoie markdown comme content:                  │
│     yield "data: {...content: markdown...}\n\n"             │
│     yield "data: [DONE]\n\n"                                │
└─────────────────────────────────────────────────────────────┘
```

---

## La Connexion Queue : Threading ↔ Async

### Le Pont de Communication

Le `queue.Queue()` est le **canal de communication** entre deux contextes d'exécution différents :

### 1. Thread en Arrière-plan (Synchrone/Bloquant)

```python
result_queue = queue.Queue()  # Crée la queue partagée

def run_generator():
    for item in generator_func(*actual_args):
        result_queue.put(('item', item))  # ← MET les items dans la queue
    result_queue.put(('done', None))

thread = threading.Thread(target=run_generator)
thread.start()  # S'exécute dans un thread séparé
```

**Ce qui se passe :**
- Le thread exécute `stream_course_generation_progress()`
- Chaque `yield` produit un item
- `result_queue.put()` **met** l'item dans la queue
- Le thread continue à travailler indépendamment

### 2. Boucle Async Principale (Asynchrone/Non-bloquant)

```python
def get_with_timeout():
    try:
        return result_queue.get(timeout=0.1)  # ← RÉCUPÈRE les items de la queue
    except queue.Empty:
        return None

result = await loop.run_in_executor(None, get_with_timeout)
```

**Ce qui se passe :**
- La boucle async appelle `get_with_timeout()` dans l'executor
- `result_queue.get()` **récupère** les items de la même queue
- Si la queue a des items → les retourne
- Si la queue est vide → retourne `None` après timeout de 0.1s

---

## Flux Visuel

```
┌─────────────────────────────────────────────────────────────────┐
│                 MÉMOIRE PARTAGÉE: queue.Queue()                 │
│                                                                  │
│     [item1] [item2] [item3] ... (FIFO - Premier Entré Premier Sorti) │
│        ↑                              ↓                          │
└────────┼──────────────────────────────┼──────────────────────────┘
         │                              │
         │ PUT                          │ GET
         │                              │
┌────────┴──────────────┐    ┌──────────┴─────────────┐
│  THREAD ARRIÈRE-PLAN  │    │   BOUCLE ASYNC         │
│  (Producteur)         │    │   (Consommateur)       │
│                       │    │                        │
│  for item in gen():   │    │  while True:           │
│    queue.put(item) ───┼───►│    result = queue.get()│
│                       │    │    yield result        │
└───────────────────────┘    └────────────────────────┘
     Bloquer OK                  Ne doit pas bloquer!
```

---

## Exemple Pas à Pas

### Temps: 0ms
```python
# Le thread démarre
result_queue = queue.Queue()  # Queue vide: []
```

### Temps: 100ms
```python
# Thread: Agent 1 print quelque chose
yield {'type': 'progress', 'content': 'Agent 1...'}
result_queue.put(('item', {...}))
# Queue maintenant: [('item', {...})]
```

### Temps: 150ms
```python
# Boucle async vérifie la queue
def get_with_timeout():
    return result_queue.get(timeout=0.1)  # Récupère l'item!

result = await loop.run_in_executor(None, get_with_timeout)
# result = ('item', {...})
# Queue maintenant: [] (vide à nouveau)
```

### Temps: 200ms
```python
# Boucle async vérifie à nouveau
def get_with_timeout():
    return result_queue.get(timeout=0.1)  # Attend 0.1s, queue toujours vide

result = await loop.run_in_executor(None, get_with_timeout)
# result = None (timeout, pas d'items)
```

### Temps: 500ms
```python
# Thread: Agent 1 termine, yield la prochaine mise à jour
yield {'type': 'progress', 'content': 'Terminé!'}
result_queue.put(('item', {...}))
# Queue maintenant: [('item', {...})]
```

### Temps: 550ms
```python
# Boucle async vérifie la queue à nouveau
result = await loop.run_in_executor(None, get_with_timeout)
# result = ('item', {...})  ← Récupéré!
```

---

## Pourquoi `run_in_executor` ?

```python
result = await loop.run_in_executor(None, get_with_timeout)
```

### Le Problème
`queue.get(timeout=0.1)` est une opération **bloquante** :
- Si la queue est vide, elle **bloque** (gèle) pendant 0.1 secondes
- Bloquer l'event loop async est **mauvais** - ça arrête toutes les autres opérations async

### La Solution
`run_in_executor(None, func)` exécute `func` dans un **pool de threads** :
- Le blocage se produit dans un thread séparé
- L'event loop async reste libre pour faire d'autres choses
- On `await` le résultat sans bloquer

**Sans executor (MAUVAIS) :**
```python
result = queue.get(timeout=0.1)  # ❌ Bloque l'event loop pendant 0.1s!
```

**Avec executor (BON) :**
```python
result = await loop.run_in_executor(None, get_with_timeout)
# ✅ Bloque un thread séparé, l'event loop est libre
```

---

## La Connexion Complète

```python
# 1. Crée la queue partagée
result_queue = queue.Queue()

# 2. Le thread met des items DEDANS
def run_generator():
    for item in generator_func():
        result_queue.put(('item', item))  # ← Producteur écrit ici

# 3. Async récupère les items DEHORS
def get_with_timeout():
    return result_queue.get(timeout=0.1)  # ← Consommateur lit depuis ici

result = await loop.run_in_executor(None, get_with_timeout)
#                                          ↑
#                          Cette fonction accède à la queue!
```

---

## Points Clés

1. **Mémoire Partagée** : Le thread et la boucle async accèdent au **même** objet `result_queue`
2. **Thread-Safe** : `queue.Queue()` est **thread-safe** - sûr à utiliser depuis plusieurs threads
3. **Producteur-Consommateur** : Le thread **produit** (put), async **consomme** (get)
4. **Async Non-Bloquant** : `run_in_executor` empêche de bloquer l'event loop
5. **Temps Réel** : Les items circulent dans la queue dès qu'ils sont produits

C'est un **pattern producteur-consommateur** classique utilisant une queue thread-safe comme pont de communication!

---

## Concepts Clés

1. **Capture Stdout** : Intercepte `print()` pour collecter les logs
2. **Pattern Générateur** : `yield` pour streamer les résultats de manière incrémentale
3. **Threading + Queue** : Exécute du code bloquant sans geler l'async
4. **Heartbeat** : Messages vides basés sur le temps pour éviter le timeout
5. **Format SSE** : `data: {...}\n\n` pour streamer vers le navigateur
6. **reasoning_content** : Champ spécial pour l'affichage de la thinking box

Cela crée une expérience en temps réel fluide où les utilisateurs voient exactement ce qui se passe pendant la génération du cours!
