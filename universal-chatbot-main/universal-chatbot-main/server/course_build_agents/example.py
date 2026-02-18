#!/usr/bin/env python3
"""
Simple example of using the multi-agent course generation system.
"""

from orchestrator import MultiAgentOrchestrator


def generate_course(subject, output_dir='./output'):
    """
    Generate a complete course for a given subject.
    
    Args:
        subject: Topic to generate course about (e.g., "Python Programming", "Deep Learning")
        output_dir: Where to save the generated course materials
    """
    
    # Configuration
    config = {
        'retriever_top_k': 5,          # Sources per query during retrieval
        'enhancer_iterations': 3,       # How many times to enhance knowledge
        'enhancer_top_k': 5,            # Sources per gap-filling query
        'output_dir': output_dir
    }
    
    # Run the multi-agent system
    orchestrator = MultiAgentOrchestrator(config)
    results = orchestrator.run(subject)
    
    return results


if __name__ == "__main__":
    import sys
    
    # Get subject from command line or use default
    subject = sys.argv[1] if len(sys.argv) > 1 else "Isolation des batiments"
    
    print(f"\n🎓 Generating course for: {subject}\n")
    
    results = generate_course(subject)
    
    print(f"\n✅ Done! Check './output/' for generated materials")
    print(f"   - initial_knowledge.md: First retrieval results")
    print(f"   - enhanced_knowledge.md: After gap-filling")
    print(f"   - course_structure.md: Complete course outline")
    print(f"   - results.json: Structured data\n")
