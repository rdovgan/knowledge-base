"""
Wiki Crew — generates and reviews wiki pages using CrewAI agents.

Handles large modules by:
  - Sending file tree summary instead of full file list
  - Limiting files read per generation
  - Agent uses FileReadTool to read specific files as needed
"""

import json
import os
from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import FileReadTool, DirectoryReadTool, FileWriterTool
import yaml
import logging

log = logging.getLogger(__name__)

# Limits
MAX_FILES_IN_PROMPT = 50     # max file paths to list in prompt
MAX_FILE_CONTENT_KB = 20     # max KB of file content to embed


def load_config():
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
    with open(os.path.join(config_dir, 'agents.yaml')) as f:
        agents_cfg = yaml.safe_load(f)
    with open(os.path.join(config_dir, 'tasks.yaml')) as f:
        tasks_cfg = yaml.safe_load(f)
    return agents_cfg, tasks_cfg


def build_llm(temperature=0.1):
    import litellm
    api_key = os.environ.get("ZAI_API_KEY")
    base_url = "https://api.z.ai/api/coding/paas/v4"
    litellm.api_key = api_key
    litellm.api_base = base_url
    return LLM(
        model="openai/glm-5-turbo",
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        custom_llm_provider="openai",
        fallbacks=[{
            "model": "openai/glm-4.7",
            "base_url": base_url,
            "api_key": api_key,
            "custom_llm_provider": "openai",
        }],
    )


def _build_file_context(file_list: list, source_path: str = None) -> str:
    """
    Build file context for the LLM prompt.
    For large file lists, shows a tree summary + representative files.
    """
    if len(file_list) <= MAX_FILES_IN_PROMPT:
        return '\n'.join(file_list)

    # Too many files — show summary + first batch
    shown = file_list[:MAX_FILES_IN_PROMPT]
    rest_count = len(file_list) - MAX_FILES_IN_PROMPT

    context = f"Showing {MAX_FILES_IN_PROMPT} of {len(file_list)} files " \
              f"({rest_count} more available via FileReadTool):\n\n"
    context += '\n'.join(shown)
    context += f"\n\n... and {rest_count} more files. Use FileReadTool to read specific files."

    return context


def run_wiki_generation(
    module_name: str,
    domain_name: str,
    file_list: list,
    output_path: str,
    wiki_filename: str,
    max_attempts: int = 3,
) -> dict:
    agents_cfg, tasks_cfg = load_config()
    llm = build_llm()

    tools = [FileReadTool(), DirectoryReadTool(), FileWriterTool()]

    generator_agent = Agent(
        role=agents_cfg['generator']['role'],
        goal=agents_cfg['generator']['goal'],
        backstory=agents_cfg['generator']['backstory'],
        llm=llm,
        tools=tools,
        verbose=False,
        max_iter=8,
        max_execution_time=300,
    )

    reviewer_agent = Agent(
        role=agents_cfg['reviewer']['role'],
        goal=agents_cfg['reviewer']['goal'],
        backstory=agents_cfg['reviewer']['backstory'],
        llm=llm,
        tools=[FileReadTool()],
        verbose=False,
        max_iter=5,
        max_execution_time=120,
    )

    file_context = _build_file_context(file_list)
    wiki_file_path = os.path.join(output_path, wiki_filename)

    for attempt in range(1, max_attempts + 1):
        log.info(f"Attempt {attempt}/{max_attempts}: "
                 f"{module_name}/{domain_name} → {wiki_filename}")

        generate_task = Task(
            description=tasks_cfg['generate_wiki_page']['description'].format(
                domain_name=domain_name,
                module_name=module_name,
                file_list=file_context,
                output_path=output_path,
                wiki_filename=wiki_filename,
            ),
            expected_output=tasks_cfg['generate_wiki_page']['expected_output'],
            agent=generator_agent,
        )

        review_task = Task(
            description=tasks_cfg['review_wiki_page']['description'].format(
                wiki_file_path=wiki_file_path,
                file_list=file_context,
                module_name=module_name,
            ),
            expected_output=tasks_cfg['review_wiki_page']['expected_output'],
            agent=reviewer_agent,
            context=[generate_task],
        )

        crew = Crew(
            agents=[generator_agent, reviewer_agent],
            tasks=[generate_task, review_task],
            process=Process.sequential,
            verbose=False,
        )

        try:
            result = crew.kickoff()
        except Exception as e:
            log.error(f"Crew execution failed: {e}")
            if attempt == max_attempts:
                return {"decision": "failed", "score": 0, "error": str(e), "attempts": attempt}
            continue

        # Parse review result
        raw = str(result.raw) if hasattr(result, 'raw') else str(result)
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0].strip()
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0].strip()

        try:
            review = json.loads(raw)
        except json.JSONDecodeError:
            decision = "approved" if "approved" in raw.lower() else "rejected"
            review = {
                "decision": decision,
                "score": 0.8 if decision == "approved" else 0.5,
                "issues": []
            }

        review['attempts'] = attempt

        log.info(f"Review: {review.get('decision')} "
                 f"(score: {review.get('score', 0)})")

        if review.get('decision') == 'approved':
            _update_frontmatter(wiki_file_path, review)
            return review

        if attempt < max_attempts:
            log.info(f"Rejected. Issues: {review.get('issues', [])}. Retrying...")
            # Add feedback for next attempt
            file_context = (
                f"PREVIOUS ATTEMPT FEEDBACK:\n{review.get('suggestions', '')}\n\n"
                f"FILES:\n" + _build_file_context(file_list)
            )

    # All attempts exhausted
    review['decision'] = 'needs-human-review'
    _update_frontmatter(wiki_file_path, review)
    return review


def _update_frontmatter(wiki_file_path: str, review: dict):
    """Update YAML front matter with review results."""
    if not os.path.exists(wiki_file_path):
        return
    with open(wiki_file_path, 'r') as f:
        content = f.read()

    status = review.get('decision', 'unknown')
    score = review.get('score', 0)
    attempts = review.get('attempts', 1)

    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            old_fm = content[:end + 3]
            new_fm = old_fm.replace(
                'status: draft',
                f'status: {status}\nreview_score: {score}\nattempts: {attempts}'
            )
            content = new_fm + content[end + 3:]
    else:
        fm = f"---\nstatus: {status}\nreview_score: {score}\nattempts: {attempts}\n---\n"
        content = fm + content

    with open(wiki_file_path, 'w') as f:
        f.write(content)
