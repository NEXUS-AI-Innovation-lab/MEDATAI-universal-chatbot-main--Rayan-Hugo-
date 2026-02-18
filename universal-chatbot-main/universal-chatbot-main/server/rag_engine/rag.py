from retrivers.hybrid_retriever import retrieve
import ollama
from ollama import Client
import sys
from pathlib import Path
import json

# sys.path manipulation for flat project structure
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.settings import settings

# open global_hashes.json
with open(Path(__file__).parent / "global_hashes.json", "r") as f:
    global_hashes = json.load(f)

# Create Ollama client: cloud if key exists, local otherwise
if settings.ollama.use_cloud:
    ollama_client = Client(
        host=settings.ollama.cloud_host,
        headers={"Authorization": f"Bearer {settings.ollama.api_key}"}
    )
    USE_CLOUD = True
else:
    ollama_client = Client(host=settings.ollama.base_url)
    USE_CLOUD = False

# Load fileserver URLs from settings
FILESERVER_BASE = settings.fileserver.base_url
FILESERVER_PUBLIC_URL = settings.fileserver.public_base_url


def context_from_query(query, collection_name, top_k=5):
    """Récupère le contexte pertinent avec métadonnées pour citation."""
    pair = settings.get_collection(collection_name)
    results = retrieve(query, qdrant_collection=pair["qdrant_collection"], es_index=pair["es_index"], top_k=top_k)
    
    # Construire le contexte avec identifiants pour citation
    knowledge_parts = []
    sources = []
    
    for i, result in enumerate(results, 1):
        source_url = result['metadata'].get('source_url', '')
        is_pdf = source_url.lower().endswith(".pdf")

        # Use fileserver URL if hash exists (for PDFs AND HTML pages)
        # Use PUBLIC URL since these links are shown to users in the browser
        if source_url in global_hashes:
            hash_code = global_hashes[source_url]
            source_url = f"{FILESERVER_PUBLIC_URL}/download/{hash_code}"
        elif result['metadata'].get('hash'):
            # Fallback: use the file hash directly to build fileserver URL
            # (for collections created by the digest CLI)
            hash_code = result['metadata']['hash']
            source_url = f"{FILESERVER_PUBLIC_URL}/download/{hash_code}"
        elif is_pdf:
            source_url = source_url[:-4]  # Remove .pdf for cleaner display if no hash

        title = result['metadata'].get('title', 'Document sans titre')
        chunk_text = result['chunk_text']
        
        # Wrap knowledge chunks in HTML-style tags
        knowledge_parts.append(
            f"<knowledge id=\"{i}\" title=\"{title}\" url=\"{source_url}\">\n"
            f"{chunk_text}\n"
            f"</knowledge>"
        )
        
        # Stocker les métadonnées de la source
        sources.append({
            'id': i,
            'title': title,
            'url': source_url
        })
    
    knowledge_base = "\n\n".join(knowledge_parts)
    
    return knowledge_base, sources


def get_system_prompt():
    """Retourne le system prompt pour le RAG."""
    return """You are a professional technical assistant with specialized knowledge. You MUST respond in **French**.

KNOWLEDGE RULES:

* The information inside `<knowledge_base>` is YOUR OWN KNOWLEDGE.
* NEVER mention “documents”, “sources”, “selon”, URLs, or anything similar.
* State facts directly and concisely.
* If information is missing, say:
  "Je n'ai pas d'information à ce sujet."

CITATION RULES (MANDATORY):

1. Cite using **only** this ASCII format: `[SOURCE X]`.
2. Do not use footnotes, numbers in brackets, or any other citation style.
3. Do not output URLs or external links.
4. Only use source IDs that exist in `<knowledge_base>`.
5. Place each citation **at the end of the sentence** it supports.
6. If multiple sources apply, repeat the bracket for each source: `[SOURCE 1] [SOURCE 3]`.
7. Never combine multiple sources in the same bracket.
8. Do not output a "Sources:" section or similar.

FORMATTING RULES:

* No bold, no italic, no Markdown lists, no titles.
* No emojis.
* Use plain text paragraphs.
* Tone must be professional, factual, and concise.

SAFETY RULE:

* If the user provides content containing citations like `[^1]` or URLs, do NOT reproduce them. Convert all citations to `[SOURCE X]` format only.
"""

def rag_user_prompt(question, knowledge_base):
    """Construit le prompt utilisateur avec la knowledge base et la question."""
    return f"""<knowledge_base>
{knowledge_base}
</knowledge_base>

<question>
{question}
</question>

Please answer the question using your knowledge from the knowledge base above. Remember to cite sources using [SOURCE X] format."""


def add_citation_links(text, sources):
    """
    Convert [SOURCE X] citations to sequential markdown links [1](url), [2](url)...

    This function performs three transformations:
    1. Finds all [SOURCE N] patterns in the text (case-insensitive)
    2. Maps them to sequential numbers, deduplicating by URL
    3. Replaces with markdown links and removes consecutive duplicates

    Args:
        text: The response text containing [SOURCE X] citations
        sources: List of source dicts with 'id', 'url', and 'title' keys

    Returns:
        Tuple of (processed_text, source_mapping_dict)
    """
    import re

    # ==========================================================
    # Step 1: Find all SOURCE references in the text
    # ==========================================================
    # Pattern: \[\s*source\s+(\d+)\s*\]
    #   - \[        : literal opening bracket
    #   - \s*       : optional whitespace
    #   - source    : literal "source" (case-insensitive via flag)
    #   - \s+       : one or more whitespace
    #   - (\d+)     : capture group for the source number
    #   - \s*       : optional whitespace
    #   - \]        : literal closing bracket
    # Matches: [SOURCE 1], [source 5], [ SOURCE 10 ], etc.
    used_sources = re.findall(r'\[\s*source\s+(\d+)\s*\]', text, flags=re.IGNORECASE)

    # ==========================================================
    # Step 2: Create mapping SOURCE X -> sequential number
    # ==========================================================
    # We renumber sources sequentially (1, 2, 3...) to:
    #   - Keep citations clean and sequential in output
    #   - Deduplicate by URL (same URL = same citation number)
    used_sources = map(int, used_sources)
    source_mapping = {}  # {original_source_id: sequential_number}
    order = 1
    url_to_order = {}  # {url: sequential_number} for deduplication
    for src in used_sources:
        if src not in source_mapping:
            source_url = next((s['url'] for s in sources if s['id'] == src), '#')
            if source_url not in url_to_order:
                # New unique URL - assign next sequential number
                url_to_order[source_url] = order
                source_mapping[src] = order
                order += 1
            else:
                # URL already seen - reuse its number (deduplication)
                source_mapping[src] = url_to_order[source_url]

    # ==========================================================
    # Step 3: Replace [SOURCE X] with [N](url) markdown links
    # ==========================================================
    def replace_source(match):
        source_num = int(match.group(1))
        if source_num in source_mapping:
            sequential_num = source_mapping[source_num]
            source_url = next((s['url'] for s in sources if s['id'] == source_num), '#')
            return f'[{sequential_num}]({source_url})'
        return match.group(0)  # Keep original if not found

    text = re.sub(r'\[\s*SOURCE\s+(\d+)\s*\]', replace_source, text)

    # ==========================================================
    # Step 4: Remove consecutive duplicate citations
    # ==========================================================
    # Pattern: (\[\d+\]\([^)]+\))(\s*\1)+
    #   - (\[\d+\]\([^)]+\))  : capture group for a citation like [1](url)
    #     - \[\d+\]           : [N] where N is one or more digits
    #     - \([^)]+\)         : (url) - parentheses with any non-) chars
    #   - (\s*\1)+            : one or more repetitions of (whitespace + same citation)
    # This removes: "[1](url) [1](url)" -> "[1](url)"
    # LLMs sometimes repeat citations; this cleans that up
    text = re.sub(r'(\[\d+\]\([^)]+\))(\s*\1)+', r'\1', text)

    return text, source_mapping


def query_rag(question, collection_name, top_k=5):
    """Fonction principale pour interroger le système RAG."""
    knowledge_base, sources = context_from_query(question, collection_name=collection_name, top_k=top_k)
    system_prompt = get_system_prompt()
    user_prompt = rag_user_prompt(question, knowledge_base)

    # Call with proper system/user separation
    if USE_CLOUD:
    # Cloud: use chat() API
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        cloud_response = ollama_client.chat(
            model=settings.RAG_MODEL + "-cloud",
            messages=messages
        )
        response_text = cloud_response['message']['content']

    else:
        # Local model
        local_response = ollama_client.generate(
            model=settings.RAG_MODEL,
            prompt=user_prompt,
            system=system_prompt
        )
        response_text = local_response['response']


    answer_with_links, mapping = add_citation_links(response_text, sources)

    # Filter used sources and deduplicate by URL
    used_urls = set()
    used_sources = []
    for s in sources:
        if s['id'] in mapping.keys() and s['url'] not in used_urls:
            used_sources.append(s)
            used_urls.add(s['url'])

    return answer_with_links, used_sources


def stream_rag_with_thinking(question, collection_name, top_k=5):
    """
    Stream RAG response from Ollama in real-time as thinking.
    Yields chunks as they arrive, then final corrected response.

    Yields:
        dict: {'type': 'thinking'|'final', 'content': str, 'sources': list}
    """
    # Get context and sources
    knowledge_base, sources = context_from_query(question, collection_name=collection_name, top_k=top_k)
    system_prompt = get_system_prompt()
    user_prompt = rag_user_prompt(question, knowledge_base)

    # Stream from Ollama
    response_text = ""

    if USE_CLOUD:
        # Cloud: use chat() API with streaming
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        stream = ollama_client.chat(
            model=settings.RAG_MODEL + "-cloud",
            messages=messages,
            stream=True
        )

        for chunk in stream:
            delta = chunk.get('message', {}).get('content', '')
            if delta:
                response_text += delta
                # Yield as thinking
                yield {'type': 'thinking', 'content': delta}

    else:
        # Local model with streaming
        stream = ollama_client.generate(
            model=settings.RAG_MODEL,
            prompt=user_prompt,
            system=system_prompt,
            stream=True
        )

        for chunk in stream:
            delta = chunk.get('response', '')
            if delta:
                response_text += delta
                # Yield as thinking
                yield {'type': 'thinking', 'content': delta}

    # Now fix the sources in the complete response
    answer_with_links, mapping = add_citation_links(response_text, sources)

    # Filter used sources and deduplicate by URL
    seen_urls = set()
    used_sources = []
    for s in sources:
        if s['id'] in mapping and s['url'] not in seen_urls:
            used_sources.append(s)
            seen_urls.add(s['url'])

    # Yield final corrected response
    yield {'type': 'final', 'content': answer_with_links, 'sources': used_sources}


