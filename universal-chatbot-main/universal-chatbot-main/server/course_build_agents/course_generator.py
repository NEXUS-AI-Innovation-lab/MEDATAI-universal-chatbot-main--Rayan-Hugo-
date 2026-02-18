from .utils import call_llm, parse_llm_json_response
from .prompts import (
    COURSE_OUTLINE_SYSTEM_PROMPT, get_course_outline_user_prompt,
    CHAPTER_DETAIL_SYSTEM_PROMPT, get_chapter_detail_user_prompt
)
import json


class CourseGeneratorAgent:
    """
    Agent 3: Generates comprehensive course structure.
    Creates chapters, subchapters, and detailed content outlines for teaching.
    """
    
    def __init__(self):
        self.course_structure = None
        
    def generate_course(self, subject, knowledge_base, sources):
        """Generate a complete course structure from the knowledge base."""
        print(f"\n📚 Agent 3 : Génération de la structure du cours sur '{subject}'...")

        # Step 1: Generate course outline
        print(f"   Étape 1 : Création du plan général du cours...")
        outline = self._generate_outline(subject, knowledge_base)
        print(f"      ✓ Plan créé avec {len(outline.get('chapters', []))} chapitres")

        # Step 2: Generate detailed chapter content
        print(f"   Étape 2 : Détail de chaque chapitre...")
        detailed_structure = self._generate_detailed_structure(subject, knowledge_base, outline)

        print(f"✅ Agent 3 : Structure du cours générée avec succès")

        self.course_structure = detailed_structure
        return detailed_structure
    
    def _generate_outline(self, subject, knowledge_base):
        """Generate high-level course outline."""
        # Use centralized prompts from prompts.py
        system_prompt = COURSE_OUTLINE_SYSTEM_PROMPT
        user_prompt = get_course_outline_user_prompt(subject, knowledge_base)

        response = call_llm(system_prompt, user_prompt)

        # Minimal fallback structure
        fallback_outline = {
            "course_title": f"Course sur {subject}",
            "description": "Course description",
            "target_audience": "Students",
            "chapters": [{"chapter_number": 1, "title": "Introduction", "description": "Introduction"}]
        }

        # Parse JSON with automatic cleanup and repair
        outline = parse_llm_json_response(
            response,
            expected_schema="""{
  "course_title": "Title in French",
  "description": "Brief course description",
  "target_audience": "Who this course is for",
  "chapters": [{"chapter_number": 1, "title": "Chapter title", "description": "What this chapter covers"}, ...]
}""",
            fallback=fallback_outline,
            context="outline generation"
        )

        return outline
    
    def _generate_detailed_structure(self, subject, knowledge_base, outline):
        """Generate detailed structure for each chapter with subchapters and content."""
        # Use centralized system prompt from prompts.py
        system_prompt = CHAPTER_DETAIL_SYSTEM_PROMPT

        detailed_chapters = []

        for chapter in outline.get('chapters', []):
            print(f"      → Chapitre {chapter['chapter_number']} : {chapter['title']}")

            # Use centralized user prompt builder from prompts.py
            user_prompt = get_chapter_detail_user_prompt(subject, knowledge_base, chapter)

            response = call_llm(system_prompt, user_prompt)

            # Minimal fallback for this chapter
            fallback_chapter = {
                "chapter_number": chapter['chapter_number'],
                "title": chapter['title'],
                "description": chapter['description'],
                "subchapters": []
            }

            # Parse JSON with automatic cleanup and repair
            chapter_detail = parse_llm_json_response(
                response,
                expected_schema=f"""{{
  "chapter_number": {chapter['chapter_number']},
  "title": "...",
  "learning_objectives": ["objective 1", ...],
  "subchapters": [{{"subchapter_number": "1.1", "title": "...", "content_to_cover": [...], ...}}]
}}""",
                fallback=fallback_chapter,
                context=f"chapter {chapter['chapter_number']} detail"
            )

            detailed_chapters.append(chapter_detail)
            subchapter_count = len(chapter_detail.get('subchapters', []))
            if subchapter_count > 0:
                print(f"         ✓ {subchapter_count} sous-chapitres créés")
            else:
                print(f"         ⚠ Chapitre {chapter['chapter_number']} sans sous-chapitres")
        
        # Assemble complete course structure
        complete_structure = {
            "course_title": outline.get('course_title', f"Course sur {subject}"),
            "description": outline.get('description', ''),
            "target_audience": outline.get('target_audience', ''),
            "total_chapters": len(detailed_chapters),
            "chapters": detailed_chapters
        }
        
        return complete_structure
    
    def get_markdown_content(self):
        """Generate markdown content as a string without saving to file."""
        if not self.course_structure:
            return "Aucune structure de cours disponible."

        md_content = []

        # Header
        md_content.append(f"# {self.course_structure['course_title']}\n")
        md_content.append(f"**Description:** {self.course_structure['description']}\n")
        md_content.append(f"**Public cible:** {self.course_structure['target_audience']}\n")
        md_content.append(f"**Nombre de chapitres:** {self.course_structure['total_chapters']}\n")
        md_content.append("---\n")

        # Chapters
        for ch_idx , chapter in enumerate(self.course_structure['chapters']):
            md_content.append(f"\n## Chapitre {ch_idx + 1}: {chapter['title']}\n")
            md_content.append(f"{chapter['description']}\n")

            if 'learning_objectives' in chapter:
                md_content.append(f"\n**Objectifs d'apprentissage:**")
                for obj in chapter['learning_objectives']:
                    md_content.append(f"- {obj}")
                md_content.append("")

            #if 'estimated_duration' in chapter:
            #    md_content.append(f"**Durée estimée:** {chapter['estimated_duration']}\n")

            # Subchapters
            if 'subchapters' in chapter:
                for sub_idx, subchapter in enumerate(chapter['subchapters']):
                    md_content.append(f"\n### {ch_idx + 1}.{sub_idx + 1} - {subchapter['title']}\n")

                    #if 'estimated_duration' in subchapter:
                    #    md_content.append(f"*Durée: {subchapter['estimated_duration']}*\n")

                    if 'content_to_cover' in subchapter:
                        md_content.append("**Contenu à couvrir:**")
                        for content in subchapter['content_to_cover']:
                            md_content.append(f"- {content}")
                        md_content.append("")

                    if 'practical_elements' in subchapter:
                        md_content.append("**Éléments pratiques:**")
                        for element in subchapter['practical_elements']:
                            md_content.append(f"- {element}")
                        md_content.append("")

            md_content.append("---")

        return '\n'.join(md_content)

    def export_to_markdown(self, output_path):
        """Export course structure to a readable markdown file."""
        if not self.course_structure:
            print("No course structure to export")
            return

        md_content = self.get_markdown_content()

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        print(f"   Course structure exported to: {output_path}")
