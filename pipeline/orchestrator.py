import json
import os
import sys
import subprocess
import logging
from datetime import datetime
from pathlib import Path
import yaml

from .crews.explorer_crew import run_explorer
from .crews.wiki_crew import run_wiki_generation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/home/r.dovgan/cakb/logs/pipeline.log'),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)


def load_modules_config() -> list:
    config_path = '/home/r.dovgan/cakb/config/modules.yaml'
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    return [m for m in cfg['modules'] if m.get('enabled', True)]


def get_module_state(module_name: str) -> dict:
    state_file = f'/home/r.dovgan/cakb/rag/{module_name}/.state.json'
    if os.path.exists(state_file):
        with open(state_file) as f:
            return json.load(f)
    return {'status': 'pending', 'completed_pages': [], 'failed_pages': []}


def save_module_state(module_name: str, state: dict):
    output_dir = f'/home/r.dovgan/cakb/rag/{module_name}'
    os.makedirs(output_dir, exist_ok=True)
    with open(f'{output_dir}/.state.json', 'w') as f:
        json.dump(state, f, indent=2)


def update_global_readme():
    modules = load_modules_config()
    lines = ['# RAG Pipeline Status\n', f'Updated: {datetime.now().isoformat()}\n\n']
    lines.append('| Module | Status | Pages | Notes |\n')
    lines.append('|--------|--------|-------|-------|\n')

    for m in modules:
        state = get_module_state(m['name'])
        status = state.get('status', 'pending')
        pages = len(state.get('completed_pages', []))
        emoji = {'pending': '⏳', 'in_progress': '🔄', 'completed': '✅', 'failed': '❌'}.get(status, '?')
        lines.append(f"| {m['name']} | {emoji} {status} | {pages} | |\n")

    with open('/home/r.dovgan/cakb/rag/README.md', 'w') as f:
        f.writelines(lines)


def process_module(module: dict):
    name = module['name']
    source_path = f"/home/r.dovgan/mbp-rag/{name}"
    output_path = f"/home/r.dovgan/cakb/rag/{name}"

    os.makedirs(output_path, exist_ok=True)
    log.info(f"Processing module: {name}")

    state = get_module_state(name)

    # Якщо вже completed — пропускаємо
    if state['status'] == 'completed':
        log.info(f"Module {name} already completed, skipping")
        return True

    state['status'] = 'in_progress'
    save_module_state(name, state)

    # Крок 1: Explorer визначає домени
    if 'plan' not in state:
        log.info(f"Running explorer for {name}...")
        plan = run_explorer(source_path, name)

        if 'error' in plan:
            log.error(f"Explorer failed for {name}: {plan['error']}")
            state['status'] = 'failed'
            save_module_state(name, state)
            return False

        state['plan'] = plan
        save_module_state(name, state)
        log.info(f"Explorer found {len(plan.get('domains', []))} domains")

    plan = state['plan']

    # Збираємо всі сторінки для генерації
    all_pages = []

    # Додаткові сторінки (overview, configuration, etc.)
    for page in plan.get('additional_pages', []):
        all_pages.append({
            'name': page['name'],
            'wiki_filename': page['wiki_filename'],
            'files': [],  # агент сам знайде
            'is_overview': True,
        })

    # Доменні сторінки
    for domain in plan.get('domains', []):
        all_pages.append({
            'name': domain['name'],
            'wiki_filename': domain.get('wiki_filename', f"{domain['name']}.md"),
            'files': domain.get('files', []),
            'is_overview': False,
        })

    # Крок 2: Генерація кожної сторінки
    for page in all_pages:
        page_name = page['name']

        # Пропускаємо вже готові
        if page_name in state.get('completed_pages', []):
            log.info(f"  Page {page_name} already done, skipping")
            continue

        log.info(f"  Generating page: {page_name}")

        review = run_wiki_generation(
            module_name=name,
            domain_name=page_name,
            file_list=page['files'],
            output_path=output_path,
            wiki_filename=page['wiki_filename'],
            max_attempts=3,
        )

        decision = review.get('decision', 'unknown')

        if decision == 'approved':
            if page_name not in state.setdefault('completed_pages', []):
                state['completed_pages'].append(page_name)
            log.info(f"  ✅ {page_name} approved (score: {review.get('score')})")
        elif decision == 'needs-human-review':
            if page_name not in state.setdefault('failed_pages', []):
                state['failed_pages'].append(page_name)
            log.warning(f"  ⚠️  {page_name} needs human review")
        else:
            if page_name not in state.setdefault('failed_pages', []):
                state['failed_pages'].append(page_name)
            log.error(f"  ❌ {page_name} failed")

        save_module_state(name, state)
        update_global_readme()

    # Генеруємо index.md для модуля
    _generate_index(name, output_path, state)

    state['status'] = 'completed'
    state['completed_at'] = datetime.now().isoformat()
    save_module_state(name, state)
    log.info(f"Module {name} completed")
    return True


def _generate_index(module_name: str, output_path: str, state: dict):
    lines = [f'# {module_name} — Wiki Index\n\n']
    lines.append(f'Generated: {datetime.now().isoformat()}\n\n')

    completed = state.get('completed_pages', [])
    failed = state.get('failed_pages', [])

    if completed:
        lines.append('## ✅ Approved Pages\n\n')
        for p in completed:
            lines.append(f'- [{p}](./{p}.md)\n')
        lines.append('\n')

    if failed:
        lines.append('## ⚠️ Needs Human Review\n\n')
        for p in failed:
            lines.append(f'- [{p}](./{p}.md)\n')

    with open(f'{output_path}/index.md', 'w') as f:
        f.writelines(lines)


def run_pipeline(single_module: str = None):
    """Головна функція. single_module для тесту одного модуля."""
    log.info("Pipeline started")
    os.makedirs('/home/r.dovgan/cakb/logs', exist_ok=True)
    os.makedirs('/home/r.dovgan/cakb/rag', exist_ok=True)

    modules = load_modules_config()

    if single_module:
        modules = [m for m in modules if m['name'] == single_module]
        if not modules:
            log.error(f"Module {single_module} not found in config")
            sys.exit(1)

    for module in modules:
        success = process_module(module)
        if not success:
            log.error(f"Pipeline stopped at module: {module['name']}")
            # Не переходимо до наступного модуля якщо поточний провалився
            sys.exit(1)

    update_global_readme()
    log.info("Pipeline completed successfully")


if __name__ == '__main__':
    module_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_pipeline(single_module=module_arg)
