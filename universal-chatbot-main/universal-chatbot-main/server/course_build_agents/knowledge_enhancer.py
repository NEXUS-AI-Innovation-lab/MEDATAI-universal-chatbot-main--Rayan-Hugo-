from .utils import context_from_query, call_llm, add_citation_links, parse_llm_json_response
from .prompts import (
    GAP_IDENTIFIER_SYSTEM_PROMPT, get_gap_identifier_user_prompt,
    KNOWLEDGE_INTEGRATION_SYSTEM_PROMPT, get_knowledge_integration_user_prompt
)
import json
import re


class KnowledgeEnhancerAgent:
    """
    Agent 2: Enhances knowledge by identifying gaps and filling them.
    Asks clarifying questions and performs additional research.
    """

    def __init__(self, max_iterations=3, top_k=5, collection_name=None):
        self.max_iterations = max_iterations
        self.top_k = top_k
        self.collection_name = collection_name
        self.enhancement_sources = []
        
    def enhance_knowledge(self, subject, initial_knowledge, initial_sources):
        """Iteratively enhance knowledge by identifying and filling gaps."""
        print(f"\n🔬 Agent 2 : Amélioration des connaissances sur '{subject}'...")

        current_knowledge = initial_knowledge
        all_sources = initial_sources.copy()

        for iteration in range(self.max_iterations):
            print(f"   Itération {iteration + 1}/{self.max_iterations}")

            # Identify gaps
            gaps = self._identify_gaps(subject, current_knowledge)

            if not gaps or len(gaps) == 0:
                print("      ✓ Aucune lacune significative trouvée")
                break

            print(f"      → {len(gaps)} lacunes identifiées")

            # Fill gaps
            enhancements = self._fill_gaps(subject, gaps, all_sources)

            if not enhancements:
                print("      ✓ Aucune nouvelle information trouvée")
                break

            # Integrate enhancements
            current_knowledge = self._integrate_enhancements(
                subject, current_knowledge, enhancements, all_sources
            )

            print(f"      ✓ {len(self.enhancement_sources)} nouvelles sources ajoutées")
            all_sources.extend(self.enhancement_sources)
            self.enhancement_sources = []

        print(f"✅ Agent 2 : Connaissances enrichies avec {len(all_sources) - len(initial_sources)} sources supplémentaires")
        return current_knowledge, all_sources
    
    def _identify_gaps(self, subject, knowledge):
        """Identify gaps, unclear points, and missing information."""
        # Use centralized prompts from prompts.py
        system_prompt = GAP_IDENTIFIER_SYSTEM_PROMPT
        user_prompt = get_gap_identifier_user_prompt(subject, knowledge)

        response = call_llm(system_prompt, user_prompt)

        # Parse JSON array from response
        gaps = parse_llm_json_response(
            response,
            expected_schema='["gap 1", "gap 2", ...]',
            fallback=[],
            context="gap identification"
        )

        # Ensure we got a list
        if not isinstance(gaps, list):
            return []

        for gap in gaps[:5]:
            print(f"         • Lacune : {gap}")

        return gaps[:5]  # Limit to 5 most important
    
    def _fill_gaps(self, subject, gaps, existing_sources):
        """Fill identified gaps using RAG queries."""
        enhancements = []
        source_id_start = max([s['id'] for s in existing_sources]) + 1 if existing_sources else 1
        
        for gap in gaps:
            # Query RAG for this gap
            knowledge_base, sources = context_from_query(gap, collection_name=self.collection_name, top_k=self.top_k)
            
            # Re-number sources
            for source in sources:
                source['original_id'] = source['id']
                source['id'] = source_id_start
                source_id_start += 1
                self.enhancement_sources.append(source)
            
            enhancements.append({
                'gap': gap,
                'knowledge': knowledge_base,
                'sources': sources
            })
        
        return enhancements
    
    def _integrate_enhancements(self, subject, current_knowledge, enhancements, all_sources):
        """Integrate new knowledge into existing knowledge base."""
        enhancement_text_parts = []
        for enh in enhancements:
            enhancement_text_parts.append(f"=== Gap: {enh['gap']} ===\n{enh['knowledge']}")

        # Use centralized prompts from prompts.py
        system_prompt = KNOWLEDGE_INTEGRATION_SYSTEM_PROMPT
        user_prompt = get_knowledge_integration_user_prompt(
            subject, current_knowledge, chr(10).join(enhancement_text_parts)
        )

        integrated = call_llm(system_prompt, user_prompt)
        
        # Add citation links
        integrated_with_links, _ = add_citation_links(integrated, all_sources + self.enhancement_sources)
        
        return integrated_with_links
