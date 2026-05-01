"""Runtime retrieval and formatting for manually approved SQL skills."""

from __future__ import annotations

from typing import Any, Dict, List

from skills.policy import MAX_ROUTED_SKILLS


def retrieve_relevant_skills(
    conversation_store: Any,
    *,
    connection_id: str,
    user_query: str,
    selected_tables: List[str],
    limit: int = MAX_ROUTED_SKILLS,
) -> List[Dict[str, Any]]:
    return conversation_store.find_matching_published_skills(
        connection_id=connection_id,
        user_query=user_query,
        selected_tables=selected_tables,
        limit=limit,
    )


def format_skills_for_prompt(skills: List[Dict[str, Any]]) -> str:
    if not skills:
        return ""

    blocks: List[str] = []
    for idx, skill in enumerate(skills, start=1):
        metadata = skill.get("metadata", {})
        blocks.append(
            "\n".join(
                [
                    f"Skill {idx}: {skill.get('title', 'Untitled Skill')}",
                    f"Match score: {skill.get('match_score', 0.0):.3f}",
                    f"Summary: {skill.get('summary', '')}",
                    f"Instructions: {skill.get('instructions', '')}",
                    f"Preferred tables: {', '.join(metadata.get('selected_tables', []))}",
                    f"Example queries: {', '.join(metadata.get('example_queries', [])[:3])}",
                ]
            )
        )
    return "\n\n".join(blocks)
