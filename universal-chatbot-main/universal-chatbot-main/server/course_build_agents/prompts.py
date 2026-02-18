"""
Course Generation Agent Prompts
================================

Centralized prompt definitions for the course generation multi-agent system.
Extracting prompts to a separate file provides:
- Easy modification without touching agent logic
- Clear overview of all LLM instructions
- Reusability across different agents

Prompt Categories:
- KNOWLEDGE_RETRIEVER_*: Prompts for search query generation and synthesis
- KNOWLEDGE_ENHANCER_*: Prompts for gap identification and integration
- COURSE_GENERATOR_*: Prompts for outline and chapter structure generation
"""

# =============================================================================
# KNOWLEDGE RETRIEVER PROMPTS
# =============================================================================

QUERY_GENERATOR_SYSTEM_PROMPT = """You are an expert research assistant.
Your task is to generate comprehensive search queries to gather all relevant knowledge about a subject.

IMPORTANT: You must respond in French."""


def get_query_generator_user_prompt(subject: str) -> str:
    """Build the user prompt for search query generation."""
    return f"""Subject: {subject}

Generate 8-10 diverse search queries that will help retrieve comprehensive knowledge about this subject.
The queries should cover:
- Core concepts and definitions
- Historical context and evolution
- Key principles and mechanisms
- Practical applications
- Advanced topics
- Common challenges and solutions
- Related technologies or methods
- Best practices

Return ONLY a JSON array of query strings, nothing else.
Example format: ["query 1", "query 2", "query 3"]"""


KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT = """You are an expert knowledge synthesizer.

IMPORTANT: You must respond in French.

Your task is to synthesize retrieved knowledge into a well-structured knowledge base.
Organize the information logically, remove duplicates, and create clear sections.

CITATION RULES:
- Cite sources using [SOURCE X] format
- Use separate brackets for multiple sources: [SOURCE 1] [SOURCE 2]
- NEVER use comma-separated sources: [SOURCE 1, 2]"""


def get_knowledge_synthesis_user_prompt(subject: str, knowledge_sections: str) -> str:
    """Build the user prompt for knowledge synthesis."""
    return f"""Subject: {subject}

<knowledge_base>
{knowledge_sections}
</knowledge_base>

Synthesize this knowledge into a comprehensive, well-organized knowledge base about {subject}.

Structure your response as:
1. Overview and definition
2. Core concepts
3. Key principles and mechanisms
4. Applications and use cases
5. Advanced topics
6. Best practices and considerations

Be thorough and cite all sources appropriately using [SOURCE X] format."""


# =============================================================================
# KNOWLEDGE ENHANCER PROMPTS
# =============================================================================

GAP_IDENTIFIER_SYSTEM_PROMPT = """You are an expert knowledge analyst.

IMPORTANT: You must respond in French.

Your task is to identify gaps, unclear explanations, and missing information in a knowledge base.
Look for:
- Important concepts that are mentioned but not explained
- Unclear or incomplete explanations
- Missing practical examples
- Lack of detail on key topics
- Questions a student might have that aren't answered"""


def get_gap_identifier_user_prompt(subject: str, knowledge: str) -> str:
    """Build the user prompt for gap identification."""
    return f"""Subject: {subject}

<knowledge_base>
{knowledge}
</knowledge_base>

Analyze this knowledge base and identify gaps or areas that need more clarification.

Return ONLY a JSON array of specific questions/gaps, nothing else.
Each question should be specific and focused.
Limit to the 5 most important gaps.

Example format: ["Question about unclear concept X", "Need more detail on Y", "How does Z work in practice?"]"""


KNOWLEDGE_INTEGRATION_SYSTEM_PROMPT = """You are an expert knowledge integrator.

IMPORTANT: You must respond in French.

Your task is to integrate new information into an existing knowledge base.
- Add the new information in the appropriate sections
- Maintain logical flow and structure
- Remove any redundancy
- Ensure consistency

CITATION RULES:
- Cite sources using [SOURCE X] format
- Use separate brackets for multiple sources: [SOURCE 1] [SOURCE 2]
- NEVER use comma-separated sources: [SOURCE 1, 2]"""


def get_knowledge_integration_user_prompt(subject: str, current_knowledge: str, enhancement_text: str) -> str:
    """Build the user prompt for knowledge integration."""
    return f"""Subject: {subject}

<current_knowledge>
{current_knowledge}
</current_knowledge>

<new_information>
{enhancement_text}
</new_information>

Integrate the new information into the current knowledge base.
Add it to the appropriate sections, maintaining structure and flow.
Keep all existing citations and add new ones for the new information.

Return the complete updated knowledge base."""


# =============================================================================
# COURSE GENERATOR PROMPTS
# =============================================================================

COURSE_OUTLINE_SYSTEM_PROMPT = """You are an expert curriculum designer.

IMPORTANT: You must respond in French.

Your task is to create a logical course outline based on the knowledge base.
Think about pedagogical progression: start with basics, build to advanced topics.

Consider:
- Prerequisites and foundational concepts first
- Logical progression of difficulty
- Balance between theory and practice
- Student learning journey"""


def get_course_outline_user_prompt(subject: str, knowledge_base: str) -> str:
    """Build the user prompt for course outline generation."""
    return f"""Subject: {subject}

<knowledge_base>
{knowledge_base}
</knowledge_base>

Create a course outline with 5-10 chapters that will teach this subject effectively to students.

IMPORTANT: the course must contain at least 5 chapters.

Return ONLY a JSON object with this structure:
{{
  "course_title": "Title in French",
  "description": "Brief course description",
  "target_audience": "Who this course is for",
  "chapters": [
    {{"chapter_number": 1, "title": "Chapter title", "description": "What this chapter covers"}},
    ...
  ]
}}"""


CHAPTER_DETAIL_SYSTEM_PROMPT = """You are an expert curriculum designer.

IMPORTANT: You must respond in French.

Your task is to create detailed chapter structures with subchapters and specific content to teach.

For each chapter:
- Break it into 3-6 logical subchapters
- For each subchapter, specify exactly what concepts, principles, or skills to teach
- Include learning objectives
- Note practical examples or exercises to include
- Suggest estimated duration"""


def get_chapter_detail_user_prompt(subject: str, knowledge_base: str, chapter: dict) -> str:
    """Build the user prompt for detailed chapter structure generation."""
    return f"""Subject: {subject}

<knowledge_base>
{knowledge_base}
</knowledge_base>

Chapter {chapter['chapter_number']}: {chapter['title']}
Description: {chapter['description']}

Create a detailed structure for this chapter.

Return ONLY a JSON object with this structure:
{{
  "chapter_number": {chapter['chapter_number']},
  "title": "{chapter['title']}",
  "description": "{chapter['description']}",
  "learning_objectives": ["objective 1", "objective 2", ...],
  "estimated_duration": "Duration estimate (e.g., 2 hours)",
  "subchapters": [
    {{
      "subchapter_number": "1.1",
      "title": "Subchapter title",
      "content_to_cover": [
        "Specific concept or skill to teach",
        "Another concept to cover",
        ...
      ],
      "practical_elements": ["Example 1", "Exercise 1", ...],
      "estimated_duration": "30 minutes"
    }},
    ...
  ]
}}"""
