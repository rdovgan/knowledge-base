"""
Explorer Crew — scans Java source code and identifies wiki pages.

For large modules (>200 files), uses domain-based exploration:
  - Module is split into top-level domains (packages)
  - Each domain is explored separately
  - Results are merged into a unified plan

For small modules, explores directly in one pass.
"""

import json
import os
import subprocess
from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import FileReadTool, DirectoryReadTool
import yaml
import logging

log = logging.getLogger(__name__)

# Limits to stay within LLM context
MAX_FILES_PER_CHUNK = 30       # files to list in one LLM call
MAX_PACKAGES_PER_CHUNK = 15    # packages to analyze per chunk
MAX_FILES_PER_DOMAIN = 80      # max files listed per domain in plan


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


# ── File system helpers ────────────────────────────────────────────

def count_java_files(path: str) -> int:
    result = subprocess.run(
        ['find', path, '-name', '*.java',
         '-not', '-path', '*/.git/*',
         '-not', '-path', '*/target/*'],
        capture_output=True, text=True
    )
    return len([f for f in result.stdout.strip().split('\n') if f])


def get_all_java_files(path: str) -> list[str]:
    result = subprocess.run(
        ['find', path, '-name', '*.java',
         '-not', '-path', '*/.git/*',
         '-not', '-path', '*/target/*'],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().split('\n') if f]


def get_file_tree_summary(source_path: str) -> str:
    """
    Build a compact tree: show directories and file counts, not individual files.
    Much smaller than listing all files.
    """
    result = subprocess.run(
        ['find', source_path, '-type', 'd',
         '-not', '-path', '*/.git/*',
         '-not', '-path ' '*/target/*'],
        capture_output=True, text=True
    )
    dirs = [d for d in result.stdout.strip().split('\n') if d]

    lines = []
    for d in sorted(dirs):
        # Count java files in this directory (not recursive)
        count_result = subprocess.run(
            ['find', d, '-maxdepth', '1', '-name', '*.java'],
            capture_output=True, text=True
        )
        count = len([f for f in count_result.stdout.strip().split('\n') if f])
        if count > 0:
            # Show relative path from source
            rel = os.path.relpath(d, source_path)
            lines.append(f"  {rel}/ ({count} files)")

    return '\n'.join(lines)


# ── LLM-based analysis ────────────────────────────────────────────

def _analyze_package_group(agent, module_name: str, package_path: str,
                           java_files: list[str]) -> dict:
    """
    Ask LLM to analyze a group of files from one package/domain.
    Returns structured JSON with domain info.
    """
    # Limit files to show
    files_to_show = java_files[:MAX_FILES_PER_CHUNK]
    files_str = '\n'.join(files_to_show)

    # Read a few key files for context (first 3, first 500 chars each)
    file_contents = ""
    for f in files_to_show[:3]:
        try:
            with open(f) as fh:
                content = fh.read(500)
            rel = os.path.relpath(f, package_path)
            file_contents += f"\n--- {rel} ---\n{content}\n"
        except Exception:
            pass

    task = Task(
        description=f"""Analyze this Java package from module '{module_name}'.

Package path: {package_path}
Files ({len(java_files)} total, showing {len(files_to_show)}):
{files_str}

Sample code:
{file_contents}

Identify:
1. What business domain this package covers
2. Key classes and their roles
3. What documentation pages would help a developer understand this code

Return JSON:
{{
  "domain_name": "<kebab-case-name>",
  "description": "<1-2 sentences what this package does>",
  "key_classes": ["<ClassName>: <1-line role>"],
  "suggested_pages": [
    {{
      "name": "<page-name>",
      "description": "<what this page should cover>",
      "wiki_filename": "<name>.md"
    }}
  ]
}}

Only return valid JSON, no other text.""",
        expected_output="Valid JSON with domain analysis",
        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )

    try:
        result = crew.kickoff()
        raw = str(result.raw) if hasattr(result, 'raw') else str(result)

        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0].strip()
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0].strip()

        return json.loads(raw)
    except Exception as e:
        log.warning(f"LLM analysis failed for {package_path}: {e}")
        return {
            "domain_name": os.path.basename(package_path).lower().replace('_', '-'),
            "description": f"Package {package_path}",
            "key_classes": [],
            "suggested_pages": [],
        }


def _explore_small_module(source_path: str, module_name: str, agent) -> dict:
    """
    Explore a small module (<200 files) in one or two LLM calls.
    """
    files = get_all_java_files(source_path)

    # Split into chunks if needed
    chunks = []
    for i in range(0, len(files), MAX_FILES_PER_CHUNK):
        chunks.append(files[i:i + MAX_FILES_PER_CHUNK])

    all_domains = []

    for i, chunk in enumerate(chunks):
        log.info(f"[Explorer] Analyzing chunk {i+1}/{len(chunks)} ({len(chunk)} files)")
        result = _analyze_package_group(agent, module_name, source_path, chunk)
        if result:
            all_domains.append(result)

    # Merge domains
    merged = _merge_domains(all_domains)

    return _build_plan(module_name, source_path, merged, files)


def _explore_domain(source_path: str, module_name: str, domain_name: str,
                    agent) -> dict:
    """
    Explore a single domain (sub-package) of a large module.
    Returns the domain's pages and file list.
    """
    files = get_all_java_files(source_path)

    # For very large domains, only list representative files
    representative_files = files[:MAX_FILES_PER_DOMAIN]

    log.info(f"[Explorer] Exploring domain {domain_name} ({len(files)} files, "
             f"showing {len(representative_files)})")

    result = _analyze_package_group(agent, module_name, source_path,
                                    representative_files)

    return {
        "domain_name": result.get("domain_name", domain_name),
        "description": result.get("description", ""),
        "key_classes": result.get("key_classes", []),
        "files": files,
        "representative_files": representative_files,
        "suggested_pages": result.get("suggested_pages", []),
    }


def _merge_domains(domain_results: list) -> list:
    """Merge domain analysis results, deduplicating."""
    merged = []
    seen_names = set()

    for d in domain_results:
        name = d.get("domain_name", "unknown")
        if name in seen_names:
            continue
        seen_names.add(name)
        merged.append(d)

    return merged


def _build_plan(module_name: str, source_path: str, domains: list,
                all_files: list) -> dict:
    """Build the exploration plan JSON."""
    # Read pom.xml for module description
    pom_path = os.path.join(source_path, 'pom.xml')
    module_description = f"Java module {module_name}"
    if os.path.exists(pom_path):
        try:
            with open(pom_path) as f:
                pom = f.read(3000)
            if '<description>' in pom:
                start = pom.find('<description>') + 13
                end = pom.find('</description>')
                if end > start:
                    module_description = pom[start:end].strip()
        except Exception:
            pass

    # Build domain pages
    domain_pages = []
    for d in domains:
        name = d.get("domain_name", "unknown")
        files = d.get("files", [])
        if not files:
            # Use representative files if available
            files = d.get("representative_files", [])

        # Use suggested pages or create one page per domain
        suggested = d.get("suggested_pages", [])
        if suggested:
            for sp in suggested:
                domain_pages.append({
                    "name": sp.get("name", name),
                    "description": sp.get("description", d.get("description", "")),
                    "wiki_filename": sp.get("wiki_filename", f"{name}.md"),
                    "files": files,
                })
        else:
            domain_pages.append({
                "name": name,
                "description": d.get("description", ""),
                "wiki_filename": f"{name}.md",
                "files": files,
            })

    plan = {
        "module_name": module_name,
        "description": module_description,
        "total_files": len(all_files),
        "domains": domain_pages,
        "additional_pages": [
            {
                "name": "overview",
                "description": "Module overview, purpose, architecture, dependencies",
                "wiki_filename": "overview.md",
                "files": [pom_path] if os.path.exists(pom_path) else []
            },
        ]
    }

    # Save plan
    plan_path = f"/home/r.dovgan/cakb/rag/{module_name}/exploration_plan.json"
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)
    with open(plan_path, 'w') as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    log.info(f"[Explorer] Plan saved to {plan_path}")

    return plan


# ── Public API ─────────────────────────────────────────────────────

def run_explorer(source_path: str, module_name: str,
                 domain_hint: str = None) -> dict:
    """
    Main entry point for exploration.

    For small modules: explores all files in 1-2 LLM calls.
    For large modules with domain_hint: explores that specific domain.
    For large modules without hint: uses decomposer to split into domains.

    Args:
        source_path: Path to the module source code
        module_name: Name of the module
        domain_hint: If set, only explore this sub-domain
    """
    from ..decomposer import decompose_module

    agents_cfg, _ = load_config()
    llm = build_llm()

    agent = Agent(
        role=agents_cfg['explorer']['role'],
        goal=agents_cfg['explorer']['goal'],
        backstory=agents_cfg['explorer']['backstory'],
        llm=llm,
        tools=[FileReadTool(), DirectoryReadTool()],
        verbose=False,
        max_iter=10,
    )

    file_count = count_java_files(source_path)
    log.info(f"[Explorer] Module {module_name}: {file_count} files"
             f"{f', domain: {domain_hint}' if domain_hint else ''}")

    # Domain hint — explore just one domain
    if domain_hint:
        return _explore_domain(source_path, module_name, domain_hint, agent)

    # Small module — explore directly
    if file_count <= 200:
        return _explore_small_module(source_path, module_name, agent)

    # Large module — decompose first, then explore each domain
    decomposition = decompose_module(module_name, source_path)
    strategy = decomposition["strategy"]
    domains = decomposition["domains"]

    log.info(f"[Explorer] Strategy: {strategy}, {len(domains)} domains")

    all_domain_pages = []
    all_files = get_all_java_files(source_path)

    for d in domains:
        domain_name = d["name"]
        domain_path = d["source_path"]
        domain_files = d["file_count"]

        log.info(f"[Explorer] Domain {domain_name}: {domain_files} files")

        if domain_files <= MAX_FILES_PER_DOMAIN:
            # Small enough to analyze in one call
            result = _explore_domain(domain_path, module_name, domain_name, agent)
            if result:
                all_domain_pages.append(result)
        else:
            # Still too large — create page from file tree summary
            log.info(f"[Explorer] Domain {domain_name} too large for LLM, "
                     f"generating page from structure")
            tree = get_file_tree_summary(domain_path)
            all_domain_pages.append({
                "domain_name": domain_name,
                "description": d.get("description", f"Domain {domain_name}"),
                "key_classes": [],
                "files": get_all_java_files(domain_path)[:MAX_FILES_PER_DOMAIN],
                "representative_files": get_all_java_files(domain_path)[:MAX_FILES_PER_DOMAIN],
                "suggested_pages": [],
                "_tree_summary": tree,
            })

    # Merge into plan
    merged = _merge_domains(all_domain_pages)
    return _build_plan(module_name, source_path, merged, all_files)
