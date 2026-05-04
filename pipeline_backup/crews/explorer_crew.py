import json
import os
import subprocess
from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import FileReadTool, DirectoryReadTool
import yaml


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

def get_directory_tree(source_path: str) -> str:
    """Отримує дерево директорій без вмісту файлів — дешева операція."""
    result = subprocess.run(
        ['find', source_path, '-type', 'f',
         '(', '-name', '*.java', '-o', '-name', '*.xml',
         '-o', '-name', '*.yml', '-o', '-name', '*.yaml',
         '-o', '-name', '*.properties', ')',
         '-not', '-path', '*/.git/*'],
        capture_output=True, text=True
    )
    files = result.stdout.strip().split('\n')
    files = [f for f in files if f]
    return '\n'.join(files)


def get_packages(source_path: str) -> list:
    """Повертає список унікальних Java пакетів."""
    result = subprocess.run(
        ['find', source_path, '-type', 'd',
         '-not', '-path', '*/.git/*',
         '-not', '-path', '*/target/*'],
        capture_output=True, text=True
    )
    dirs = result.stdout.strip().split('\n')
    # Залишаємо тільки java пакети
    packages = [d for d in dirs if '/java/' in d and d.strip()]
    return packages


def chunk_packages(packages: list, max_chunk_size: int = 20) -> list:
    """Ділить пакети на chunks для обробки."""
    chunks = []
    for i in range(0, len(packages), max_chunk_size):
        chunks.append(packages[i:i + max_chunk_size])
    return chunks


def get_files_for_packages(packages: list) -> list:
    """Повертає всі Java файли для списку пакетів."""
    files = []
    for pkg in packages:
        result = subprocess.run(
            ['find', pkg, '-maxdepth', '1', '-name', '*.java'],
            capture_output=True, text=True
        )
        pkg_files = [f for f in result.stdout.strip().split('\n') if f]
        files.extend(pkg_files)
    return files


def analyze_chunk(agent, tasks_cfg, source_path: str,
                  module_name: str, chunk_packages: list,
                  chunk_index: int) -> dict:
    """Аналізує один chunk пакетів."""
    files = get_files_for_packages(chunk_packages)
    packages_str = '\n'.join(chunk_packages)
    files_str = '\n'.join(files[:100])  # максимум 100 файлів на chunk

    task = Task(
        description=f"""Analyze this subset of packages from module '{module_name}' (chunk {chunk_index}).

Packages to analyze:
{packages_str}

Files in these packages:
{files_str}

For each package identify:
1. What logical domain/component it belongs to
2. What business purpose it serves
3. Key classes and their roles

Return JSON:
{{
  "chunk_index": {chunk_index},
  "domains": [
    {{
      "name": "<domain_name>",
      "description": "<what this domain covers>",
      "packages": ["<package_path>"],
      "files": ["<file_path>"],
      "estimated_complexity": "low|medium|high"
    }}
  ]
}}

Only return valid JSON, no other text.""",
        expected_output="Valid JSON with domains array",
        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )

    result = crew.kickoff()
    raw = str(result.raw) if hasattr(result, 'raw') else str(result)

    if '```json' in raw:
        raw = raw.split('```json')[1].split('```')[0].strip()
    elif '```' in raw:
        raw = raw.split('```')[1].split('```')[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"chunk_index": chunk_index, "domains": []}


def merge_domains(all_chunk_results: list) -> list:
    """Об'єднує домени з усіх chunks, уникаючи дублікатів."""
    domain_map = {}

    for chunk_result in all_chunk_results:
        for domain in chunk_result.get('domains', []):
            name = domain['name']
            if name in domain_map:
                # Об'єднуємо файли і пакети
                domain_map[name]['files'].extend(domain.get('files', []))
                domain_map[name]['packages'].extend(domain.get('packages', []))
                # Беремо вищу складність
                complexity_order = {'low': 1, 'medium': 2, 'high': 3}
                current = complexity_order.get(domain_map[name]['estimated_complexity'], 1)
                new = complexity_order.get(domain.get('estimated_complexity', 'low'), 1)
                if new > current:
                    domain_map[name]['estimated_complexity'] = domain.get('estimated_complexity')
            else:
                domain_map[name] = {
                    'name': name,
                    'description': domain.get('description', ''),
                    'packages': domain.get('packages', []),
                    'files': domain.get('files', []),
                    'estimated_complexity': domain.get('estimated_complexity', 'medium'),
                    'wiki_filename': f"{name.lower().replace(' ', '-')}.md"
                }

    # Дедублікуємо файли
    for domain in domain_map.values():
        domain['files'] = list(set(domain['files']))
        domain['packages'] = list(set(domain['packages']))

    return list(domain_map.values())


def run_explorer(source_path: str, module_name: str) -> dict:
    """
    Chunked exploration — працює для модулів будь-якого розміру.
    Ділить пакети на chunks по 20, аналізує кожен окремо,
    потім об'єднує результати.
    """
    agents_cfg, tasks_cfg = load_config()
    llm = build_llm()

    print(f"\n[Explorer] Scanning directory structure of {module_name}...")
    all_packages = get_packages(source_path)
    total_files = get_directory_tree(source_path).count('\n') + 1

    print(f"[Explorer] Found {len(all_packages)} packages, ~{total_files} files")

    # Читаємо pom.xml окремо
    pom_path = os.path.join(source_path, 'pom.xml')
    pom_content = ""
    if os.path.exists(pom_path):
        with open(pom_path) as f:
            pom_content = f.read()[:3000]  # перші 3000 символів

    explorer_agent = Agent(
        role=agents_cfg['explorer']['role'],
        goal=agents_cfg['explorer']['goal'],
        backstory=agents_cfg['explorer']['backstory'],
        llm=llm,
        tools=[FileReadTool(), DirectoryReadTool()],
        verbose=True,
        max_iter=10,
    )

    # Ділимо пакети на chunks
    chunks = chunk_packages(all_packages, max_chunk_size=20)
    print(f"[Explorer] Processing {len(chunks)} chunks...")

    all_chunk_results = []
    for i, chunk in enumerate(chunks):
        print(f"[Explorer] Analyzing chunk {i+1}/{len(chunks)}...")
        result = analyze_chunk(
            explorer_agent, tasks_cfg,
            source_path, module_name, chunk, i
        )
        all_chunk_results.append(result)

    # Об'єднуємо всі домени
    merged_domains = merge_domains(all_chunk_results)
    print(f"[Explorer] Identified {len(merged_domains)} domains after merging")

    # Визначаємо модуль опис через pom.xml
    module_description = f"Java module {module_name}"
    if pom_content:
        if '<description>' in pom_content:
            start = pom_content.find('<description>') + 13
            end = pom_content.find('</description>')
            if end > start:
                module_description = pom_content[start:end].strip()

    plan = {
        "module_name": module_name,
        "description": module_description,
        "total_files": total_files,
        "total_packages": len(all_packages),
        "domains": merged_domains,
        "additional_pages": [
            {
                "name": "overview",
                "description": "Module overview, purpose, architecture, dependencies, quick start",
                "wiki_filename": "overview.md",
                "files": [pom_path] if os.path.exists(pom_path) else []
            },
            {
                "name": "configuration",
                "description": "All configuration files, Spring beans, properties, env variables",
                "wiki_filename": "configuration.md",
                "files": []
            }
        ]
    }

    # Зберігаємо план
    plan_path = f"/home/r.dovgan/cakb/rag/{module_name}/exploration_plan.json"
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)
    with open(plan_path, 'w') as f:
        json.dump(plan, f, indent=2)
    print(f"[Explorer] Plan saved to {plan_path}")

    return plan
