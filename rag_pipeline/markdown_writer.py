"""
Markdown writer — generates structured Markdown from parsed data.

Two types of output:
1. Per-domain overview pages (for LLM enrichment later)
2. Per-class detail pages (deterministic, no LLM needed)

All files are written to disk immediately — 100% reliable.
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict

log = logging.getLogger(__name__)


def write_class_page(cls: dict, output_dir: str) -> str:
    """
    Write a single class Markdown page.
    Returns the file path.
    """
    name = cls.get('name', 'Unknown')
    package = cls.get('package', '')
    module = cls.get('module', '')
    class_type = cls.get('class_type', 'class')
    file_path = cls.get('file_path', '')

    lines = []
    lines.append(f"# {name}")
    lines.append("")
    lines.append(f"- **Package:** `{package}`")
    lines.append(f"- **Module:** {module}")
    lines.append(f"- **Type:** {class_type}")

    if cls.get('extends'):
        lines.append(f"- **Extends:** `{cls['extends']}`")
    if cls.get('implements'):
        impl = ', '.join(f"`{i}`" for i in cls['implements'])
        lines.append(f"- **Implements:** {impl}")
    if cls.get('spring_stereotype'):
        lines.append(f"- **Stereotype:** `{cls['spring_stereotype']}`")
    if cls.get('request_mappings'):
        mappings = ', '.join(f"`{m}`" for m in cls['request_mappings'])
        lines.append(f"- **Endpoints:** {mappings}")
    if file_path:
        rel = file_path.replace('/home/r.dovgan/mbp-rag/', '')
        lines.append(f"- **Source:** `{rel}`")

    lines.append("")

    # Javadoc
    if cls.get('javadoc'):
        lines.append("## Overview")
        lines.append("")
        lines.append(cls['javadoc'])
        lines.append("")

    # Annotations
    if cls.get('annotations'):
        lines.append("## Class Annotations")
        lines.append("")
        for ann in cls['annotations']:
            if ann.get('params'):
                lines.append(f"- `@{ann['name']}({ann['params']})`")
            else:
                lines.append(f"- `@{ann['name']}`")
        lines.append("")

    # Fields
    if cls.get('fields'):
        lines.append("## Fields")
        lines.append("")
        lines.append("| Type | Name | Annotations |")
        lines.append("|------|------|-------------|")
        for f in cls['fields']:
            anns = ', '.join(f"@{a['name']}" for a in f.get('annotations', []))
            lines.append(f"| `{f['type_name']}` | `{f['name']}` | {anns} |")
        lines.append("")

    # Methods
    if cls.get('methods'):
        lines.append("## Methods")
        lines.append("")
        for m in cls['methods']:
            ret = m.get('return_type', 'void')
            params = m.get('parameters', '')
            anns = [f"@{a['name']}" for a in m.get('annotations', [])]
            ann_str = f" ({', '.join(anns)})" if anns else ""

            lines.append(f"### `{ret} {m['name']}({params})`{ann_str}")
            lines.append("")

            if m.get('javadoc'):
                lines.append(m['javadoc'])
                lines.append("")

    # Settings references
    if cls.get('settings_refs'):
        lines.append("## Configuration References")
        lines.append("")
        lines.append("| Setting Key | Default | Source |")
        lines.append("|-------------|---------|--------|")
        for sref in cls['settings_refs']:
            lines.append(f"| `{sref['setting_key']}` | `{sref.get('default_value', '')}` | {sref.get('source_annotation', '')} |")
        lines.append("")

    # Branching logic
    if cls.get('branching_logic'):
        lines.append("## Settings-Driven Branching")
        lines.append("")
        for bl in cls['branching_logic']:
            lines.append(f"- **`{bl['setting_key']}`** → `{bl['condition_type']}` in `{bl.get('method_name', '(class body)')}`")
            lines.append(f"  ```java")
            lines.append(f"  {bl.get('condition_text', '')[:150]}")
            lines.append(f"  ```")
            lines.append("")

    # Write file
    package_dir = package.replace('.', '/')
    dir_path = os.path.join(output_dir, module, package_dir)
    os.makedirs(dir_path, exist_ok=True)

    file_name = f"{name}.md"
    full_path = os.path.join(dir_path, file_name)

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return full_path


def write_domain_page(domain: dict, classes: List[dict], output_dir: str) -> str:
    """
    Write a domain overview page with summary of all classes.
    This is the page that LLM will enrich later.
    """
    domain_name = domain.get('name', 'unknown')
    module = domain.get('module', '')
    channel = domain.get('channel', '')
    packages = domain.get('packages', [])

    # Skip if already enriched — don't overwrite LLM-generated content
    safe_name = domain_name.replace('/', '_').replace(' ', '_')
    full_path = os.path.join(output_dir, module, '_domains', f"{safe_name}.md")

    if os.path.exists(full_path):
        with open(full_path, 'r', encoding='utf-8') as f:
            head = f.read(200)
        if 'status: enriched' in head:
            return full_path  # Preserve enriched content

    lines = []
    lines.append(f"---")
    lines.append(f"domain: {domain_name}")
    lines.append(f"module: {module}")
    if channel:
        lines.append(f"channel: {channel}")
    lines.append(f"generated_at: {datetime.now().isoformat()}")
    lines.append(f"status: parsed")
    lines.append(f"---")
    lines.append("")
    lines.append(f"# Domain: {domain_name}")
    lines.append("")
    lines.append(f"- **Module:** {module}")
    if channel:
        lines.append(f"- **Channel:** {channel}")
    lines.append(f"- **Packages:** {len(packages)}")
    lines.append(f"- **Classes:** {domain.get('class_count', 0)}")
    lines.append("")

    # Packages list
    if packages:
        lines.append("## Packages")
        lines.append("")
        for pkg in packages:
            lines.append(f"- `{pkg}`")
        lines.append("")

    # Class summary table
    lines.append("## Classes")
    lines.append("")
    lines.append("| Class | Type | Stereotype | Key Dependencies |")
    lines.append("|-------|------|------------|------------------|")

    for cls in classes:
        name = cls.get('name', '')
        ctype = cls.get('class_type', '')
        stereo = cls.get('spring_stereotype', '')

        # Key dependencies from @Autowired fields
        deps = []
        for f in cls.get('fields', []):
            for a in f.get('annotations', []):
                if a.get('name') == 'Autowired':
                    deps.append(f['type_name'])
                    break
        dep_str = ', '.join(deps[:5])
        if len(deps) > 5:
            dep_str += f" (+{len(deps)-5})"

        # Link to class page
        pkg = cls.get('package', '').replace('.', '/')
        link = f"[{name}](./{pkg}/{name}.md)" if pkg else name

        lines.append(f"| {link} | {ctype} | {stereo} | {dep_str} |")

    lines.append("")

    # Settings map
    if domain.get('settings_map'):
        lines.append("## Configuration Settings")
        lines.append("")
        lines.append("| Setting Key | Used In | Source |")
        lines.append("|-------------|---------|--------|")
        for key, refs in domain['settings_map'].items():
            classes_str = ', '.join(set(r.get('context', '') for r in refs[:3]))
            source = refs[0].get('source_annotation', '') if refs else ''
            lines.append(f"| `{key}` | {classes_str} | {source} |")
        lines.append("")

    # REST API endpoints
    all_endpoints = []
    for cls in classes:
        for ep in cls.get('request_mappings', []):
            all_endpoints.append((ep, cls.get('name', '')))
    if all_endpoints:
        lines.append("## REST API Endpoints")
        lines.append("")
        for ep, cls_name in all_endpoints:
            lines.append(f"- `{ep}` — {cls_name}")
        lines.append("")

    # Placeholder for LLM enrichment
    lines.append("## Architecture & Business Logic")
    lines.append("")
    lines.append("<!-- LLM_ENRICHMENT_PLACEHOLDER -->")
    lines.append("")
    lines.append("*This section will be filled by LLM enrichment.*")
    lines.append("")

    # Write file
    dir_path = os.path.join(output_dir, module, '_domains')
    os.makedirs(dir_path, exist_ok=True)

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return full_path


def write_module_index(module_name: str, domains: List[dict], output_dir: str) -> str:
    """Write module index page."""
    lines = []
    lines.append(f"# Module: {module_name}")
    lines.append("")
    lines.append(f"**Domains:** {len(domains)}")
    lines.append(f"**Total classes:** {sum(d.get('class_count', 0) for d in domains)}")
    lines.append("")

    # Channel domains first
    channel_domains = [d for d in domains if d.get('channel')]
    other_domains = [d for d in domains if not d.get('channel')]

    if channel_domains:
        lines.append("## Channel Integrations")
        lines.append("")
        for d in sorted(channel_domains, key=lambda x: x.get('channel', '')):
            safe_name = d['name'].replace('/', '_').replace(' ', '_')
            lines.append(f"- [{d['name']}](./_domains/{safe_name}.md) — "
                        f"{d.get('channel', '')} ({d.get('class_count', 0)} classes)")
        lines.append("")

    if other_domains:
        lines.append("## Core Domains")
        lines.append("")
        for d in sorted(other_domains, key=lambda x: x.get('name', '')):
            safe_name = d['name'].replace('/', '_').replace(' ', '_')
            lines.append(f"- [{d['name']}](./_domains/{safe_name}.md) — "
                        f"{d.get('class_count', 0)} classes, "
                        f"{len(d.get('packages', []))} packages")
        lines.append("")

    # Write
    dir_path = os.path.join(output_dir, module_name)
    os.makedirs(dir_path, exist_ok=True)
    full_path = os.path.join(dir_path, 'index.md')

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return full_path


def write_root_index(modules_data: dict, output_dir: str) -> str:
    """Write root index page linking all modules."""
    lines = []
    lines.append("# MyBookingPal — RAG Knowledge Base")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("")

    total_classes = 0
    total_domains = 0

    for mod in modules_data.get('modules', []):
        stats = mod.get('stats', {})
        module_name = mod.get('module', '')
        classes = stats.get('classes_parsed', 0)
        total_classes += classes
        lines.append(f"## [{module_name}](./{module_name}/index.md)")
        lines.append(f"- Java classes: {classes}")
        lines.append(f"- Properties files: {stats.get('properties_files', 0)}")
        lines.append(f"- MyBatis mappers: {stats.get('mapper_files', 0)}")
        lines.append("")

    lines.insert(3, f"**Total classes:** {total_classes}")
    lines.insert(4, f"**Modules:** {len(modules_data.get('modules', []))}")
    lines.insert(5, "")

    full_path = os.path.join(output_dir, 'index.md')
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return full_path


def generate_all_markdown(parsed_data: dict, domains: List[dict], output_dir: str) -> dict:
    """
    Generate all Markdown files from parsed data.

    Returns stats dict.
    """
    os.makedirs(output_dir, exist_ok=True)

    class_files_written = 0
    domain_files_written = 0

    # Build class lookup: name → class dict
    class_lookup = {}
    for mod in parsed_data.get('modules', []):
        for cls in mod.get('classes', []):
            key = f"{cls.get('module', '')}:{cls.get('name', '')}"
            class_lookup[key] = cls

    # Write class pages
    for mod in parsed_data.get('modules', []):
        module_name = mod.get('module', '')
        for cls in mod.get('classes', []):
            try:
                write_class_page(cls, output_dir)
                class_files_written += 1
            except Exception as e:
                log.warning(f"Failed to write class page for {cls.get('name', '?')}: {e}")

        if class_files_written % 1000 == 0:
            log.info(f"  Written {class_files_written} class pages...")

    # Write domain pages
    modules_domains = {}
    for domain in domains:
        module = domain.get('module', '')
        if module not in modules_domains:
            modules_domains[module] = []
        modules_domains[module].append(domain)

        # Get classes for this domain
        domain_classes = []
        for cls_name in domain.get('class_names', []):
            key = f"{module}:{cls_name}"
            if key in class_lookup:
                domain_classes.append(class_lookup[key])

        try:
            write_domain_page(domain, domain_classes, output_dir)
            domain_files_written += 1
        except Exception as e:
            log.warning(f"Failed to write domain page for {domain.get('name', '?')}: {e}")

    # Write module indices
    for module_name, module_domains in modules_domains.items():
        write_module_index(module_name, module_domains, output_dir)

    # Write root index
    write_root_index(parsed_data, output_dir)

    log.info(f"Markdown generated: {class_files_written} class pages, "
             f"{domain_files_written} domain pages")

    return {
        "class_pages": class_files_written,
        "domain_pages": domain_files_written,
    }
