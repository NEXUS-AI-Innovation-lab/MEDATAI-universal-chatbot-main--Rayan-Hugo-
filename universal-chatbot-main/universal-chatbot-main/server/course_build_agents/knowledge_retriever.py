from .utils import context_from_query, call_llm, add_citation_links, parse_llm_json_response
from .prompts import (
    QUERY_GENERATOR_SYSTEM_PROMPT, get_query_generator_user_prompt,
    KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT, get_knowledge_synthesis_user_prompt
)
import json


class KnowledgeRetrieverAgent:
    """
    Agent 1: Retrieves comprehensive knowledge on a subject.
    Generates multiple queries to cover all aspects of the topic.
    """

    def __init__(self, top_k_per_query=5, collection_name=None):
        self.top_k_per_query = top_k_per_query
        self.collection_name = collection_name
        self.all_sources = []
        
    def generate_search_queries(self, subject):
        """Generate multiple search queries to cover the subject comprehensively."""
        # Use centralized prompts from prompts.py
        system_prompt = QUERY_GENERATOR_SYSTEM_PROMPT
        user_prompt = get_query_generator_user_prompt(subject)

        response = call_llm(system_prompt, user_prompt)

        # Fallback queries if parsing fails
        fallback_queries = [
            subject,
            f"{subject} concepts fondamentaux",
            f"{subject} principes",
            f"{subject} applications pratiques",
            f"{subject} techniques avancées"
        ]

        # Parse JSON array from response
        queries = parse_llm_json_response(
            response,
            expected_schema='["query 1", "query 2", "query 3", ...]',
            fallback=fallback_queries,
            context="search query generation"
        )

        # Ensure we got a list
        if not isinstance(queries, list):
            return fallback_queries

        return queries
    
    def retrieve_knowledge(self, subject):
        """Retrieve and structure knowledge from multiple queries."""
        print(f"📚 Agent 1 : Collecte des connaissances sur '{subject}'...")

        # Generate diverse queries
        queries = self.generate_search_queries(subject)
        print(f"   {len(queries)} requêtes de recherche générées")

        # Retrieve knowledge for each query
        all_knowledge = []
        source_id_counter = 1

        for idx, query in enumerate(queries, 1):
            print(f"   Requête {idx}/{len(queries)} : {query[:60]}...")
            knowledge_base, sources = context_from_query(query, collection_name=self.collection_name, top_k=self.top_k_per_query)

            # Re-number sources to avoid conflicts
            for source in sources:
                source['original_id'] = source['id']
                source['id'] = source_id_counter
                source_id_counter += 1
                self.all_sources.append(source)

            print(f"      ✓ {len(sources)} sources trouvées")

            all_knowledge.append({
                'query': query,
                'knowledge': knowledge_base,
                'sources': sources
            })

        # Synthesize all knowledge
        synthesized = self._synthesize_knowledge(subject, all_knowledge)

        print(f"✅ Agent 1 : Connaissances récupérées depuis {len(self.all_sources)} sources")
        return synthesized, self.all_sources
    
    def _synthesize_knowledge(self, subject, all_knowledge):
        """Synthesize retrieved knowledge into structured format."""
        # Build comprehensive knowledge base
        knowledge_sections = []
        for idx, kb in enumerate(all_knowledge, 1):
            knowledge_sections.append(f"=== Search Query {idx}: {kb['query']} ===\n{kb['knowledge']}")

        # Use centralized prompts from prompts.py
        system_prompt = KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT
        user_prompt = get_knowledge_synthesis_user_prompt(subject, chr(10).join(knowledge_sections))

        synthesized = call_llm(system_prompt, user_prompt)
        
        # Add citation links
        synthesized_with_links, _ = add_citation_links(synthesized, self.all_sources)
        
        return synthesized_with_links
