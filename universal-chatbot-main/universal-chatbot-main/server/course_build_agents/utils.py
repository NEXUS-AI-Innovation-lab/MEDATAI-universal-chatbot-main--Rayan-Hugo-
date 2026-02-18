from retrivers.hybrid_retriever import retrieve
import ollama
from ollama import Client
import re
import json
import sys
from pathlib import Path

# sys.path manipulation for flat project structure
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.settings import settings

# Load global_hashes.json for PDF URL conversion (same as RAG)
global_hashes = {}
global_hashes_path = Path(__file__).parent.parent / "rag_engine" / "global_hashes.json"
if global_hashes_path.exists():
    try:
        with open(global_hashes_path, "r") as f:
            global_hashes = json.load(f)
    except Exception:
        pass

# Load fileserver URLs from settings
FILESERVER_BASE = settings.fileserver.base_url
FILESERVER_PUBLIC_URL = settings.fileserver.public_base_url

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



def context_from_query(query, collection_name=None, top_k=5):
    """Récupère le contexte pertinent avec métadonnées pour citation."""
    if collection_name is None:
        collection_name = next(iter(settings.COLLECTIONS))
        print(f"[WARN] No collection_name provided to context_from_query, defaulting to '{collection_name}'")
    pair = settings.get_collection(collection_name)
    results = retrieve(query, qdrant_collection=pair["qdrant_collection"], es_index=pair["es_index"], top_k=top_k)

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

        knowledge_parts.append(
            f"<knowledge id=\"{i}\" title=\"{title}\" url=\"{source_url}\">\n"
            f"{chunk_text}\n"
            f"</knowledge>"
        )

        sources.append({
            'id': i,
            'title': title,
            'url': source_url,
            'chunk_text': chunk_text
        })

    knowledge_base = "\n\n".join(knowledge_parts)
    return knowledge_base, sources


def add_citation_links(text, sources):
    """Convertit [SOURCE X] en citations séquentielles [1](url), [2](url)..."""
    used_sources = re.findall(r'\[\s*SOURCE\s+(\d+)\s*\]', text)

    # Create mapping SOURCE X -> sequential number (deduplicated by URL)
    used_sources_list = list(map(int, used_sources))
    source_mapping = {}
    order = 1
    url_to_order = {}
    for src in used_sources_list:
        if src not in source_mapping:
            source_url = next((s['url'] for s in sources if s['id'] == src), '#')
            if source_url not in url_to_order:
                url_to_order[source_url] = order
                source_mapping[src] = order
                order += 1
            else:
                source_mapping[src] = url_to_order[source_url]

    def replace_source(match):
        source_num = int(match.group(1))
        if source_num in source_mapping:
            sequential_num = source_mapping[source_num]
            source_url = next((s['url'] for s in sources if s['id'] == source_num), '#')
            return f'[{sequential_num}]({source_url})'
        return match.group(0)

    text = re.sub(r'\[\s*SOURCE\s+(\d+)\s*\]', replace_source, text)

    # Remove consecutive duplicate citations (e.g., "[1](url) [1](url)" -> "[1](url)")
    text = re.sub(r'(\[\d+\]\([^)]+\))(\s*\1)+', r'\1', text)

    return text, source_mapping


def call_llm(system_prompt, user_prompt, model=None):
    """Wrapper pour appeler le LLM avec system et user prompts."""
    if model is None:
        model = settings.RAG_MODEL
    
    if USE_CLOUD:
        # Cloud: use chat() API
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        cloud_response = ollama_client.chat(
            model=model + "-cloud",
            messages=messages
        )
        return cloud_response['message']['content']
    else:
        # Local: use generate() API
        local_response = ollama_client.generate(
            model=model,
            prompt=user_prompt,
            system=system_prompt
        )
        return local_response['response']


def call_llm_structured_output(system_prompt, user_prompt,schema, model=None):
    """Wrapper pour appeler le LLM avec system et user prompts."""
    if model is None:
        model = settings.RAG_MODEL
    
    if USE_CLOUD:
        # Cloud: use chat() API
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        cloud_response = ollama_client.chat(
            model=model + "-cloud",
            messages=messages,
            format=schema
        )
        return cloud_response['message']['content']
    else:
        # Local: use generate() API
        local_response = ollama_client.generate(
            model=model,
            prompt=user_prompt,
            system=system_prompt
        )
        return local_response['response']

def parse_llm_json_response(response: str, expected_schema: str, fallback=None, context: str = ""):
    """
    Parse JSON from an LLM response with automatic cleanup and repair.

    This function handles common issues with LLM-generated JSON:
    1. Strips markdown code fences (```json ... ```)
    2. Finds JSON object/array boundaries
    3. Attempts parsing, with LLM repair fallback

    Args:
        response: Raw LLM response text
        expected_schema: Description of expected JSON structure (for repair prompts)
        fallback: Value to return if all parsing fails (default: None)
        context: Description of what was being parsed (for error messages)

    Returns:
        Parsed dict/list or fallback value

    Example:
        result = parse_llm_json_response(
            response,
            '{"questions": ["q1", "q2", ...]}',
            fallback={"questions": []},
            context="question generation"
        )
    """
    if not response:
        if context:
            print(f"   [{context}] Empty response received")
        return fallback

    try:
        # Step 1: Clean the response
        response = response.strip()

        # Step 2: Remove markdown code fences if present
        if response.startswith('```'):
            response = re.sub(r'^```(?:json)?\s*\n?', '', response)
            response = re.sub(r'\n?```\s*$', '', response)

        # Step 3: Find JSON boundaries
        # Look for object {...} or array [...]
        obj_start = response.find('{')
        arr_start = response.find('[')

        if obj_start == -1 and arr_start == -1:
            raise ValueError("No JSON object or array found in response")

        # Use whichever comes first (or the one that exists)
        if obj_start == -1:
            start, end_char = arr_start, ']'
        elif arr_start == -1:
            start, end_char = obj_start, '}'
        else:
            if obj_start < arr_start:
                start, end_char = obj_start, '}'
            else:
                start, end_char = arr_start, ']'

        end = response.rfind(end_char) + 1
        if end <= start:
            raise ValueError(f"Could not find closing '{end_char}'")

        json_str = response[start:end]

        # Step 4: Parse
        result = json.loads(json_str)
        return result

    except (json.JSONDecodeError, ValueError) as e:
        if context:
            print(f"   [{context}] JSON parsing failed: {e}")
        else:
            print(f"   JSON parsing failed: {e}")

        # Step 5: Attempt LLM repair
        fixed = fix_malformed_json(response, expected_schema, str(e))
        if fixed:
            try:
                return json.loads(fixed)
            except Exception as repair_error:
                if context:
                    print(f"   [{context}] Repair also failed: {repair_error}")

        return fallback

    except Exception as e:
        if context:
            print(f"   [{context}] Unexpected error: {e}")
        else:
            print(f"   Unexpected error during JSON parsing: {e}")
        return fallback


def fix_malformed_json(broken_json, expected_structure_description, error_message):
    """
    Failsafe function that asks LLM to fix malformed JSON.

    This is called as a last resort when parse_llm_json_response fails.
    Uses the LLM's ability to understand and repair JSON structure.

    Args:
        broken_json: The string that failed to parse
        expected_structure_description: Description of what the JSON should look like
        error_message: The error message from json.loads()

    Returns:
        Corrected JSON string or None if correction fails
    """
    system_prompt = """You are a JSON repair specialist.

Your ONLY task is to fix malformed JSON and return valid, parsable JSON.

Common issues you fix:
- Missing or extra commas
- Unclosed brackets or braces
- Unescaped quotes in strings
- Trailing commas before closing brackets
- Missing quotes around keys
- Single quotes instead of double quotes
- Comments in JSON (which are invalid)

CRITICAL RULES:
1. Return ONLY valid JSON - nothing else
2. Do not add explanations or markdown
3. Do not wrap in code blocks
4. Preserve all content from the original
5. Only fix structural/syntax issues
6. Ensure proper encoding of special characters"""

    user_prompt = f"""The following JSON failed to parse with this error:
ERROR: {error_message}

BROKEN JSON:
{broken_json}

EXPECTED STRUCTURE:
{expected_structure_description}

Fix this JSON and return ONLY the corrected, valid JSON. No explanations, no markdown, just valid JSON."""

    try:
            corrected = call_llm(system_prompt, user_prompt)
            
            # Try to extract JSON if LLM wrapped it in markdown or text
            corrected = corrected.strip()
            
            # Remove markdown code blocks if present
            if corrected.startswith('```'):
                corrected = re.sub(r'^```(?:json)?\s*\n?', '', corrected)
                corrected = re.sub(r'\n?```\s*$', '', corrected)
            
            # Try to find JSON object
            start = corrected.find('{')
            end = corrected.rfind('}') + 1
            if start != -1 and end > start:
                corrected = corrected[start:end]
            
            # Validate it parses
            json.loads(corrected)
            print(f"   ✓ JSON successfully repaired by LLM")
            return corrected
            
    except Exception as repair_error:
            print(f"   ✗ Failed to repair JSON: {repair_error}")
            return None