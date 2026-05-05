"""
LLM Enricher — adds business context to domain pages.

Receives pre-parsed class structure (no hallucination risk).
One LLM call per domain (~200-500 calls total).
"""

import os
import re
import json
import time
import logging
from typing import List, Dict, Optional

log = logging.getLogger(__name__)


def build_llm_client(api_key: str, base_url: str):
    """Build OpenAI-compatible client."""
    from openai import OpenAI
    return OpenAI(api_key=api_key, base_url=base_url)


def build_enrichment_prompt(domain: dict, classes: List[dict]) -> str:
    """
    Build the LLM prompt for domain enrichment.
    Only uses data from the parser — no raw source code.
    """
    domain_name = domain.get('name', '')
    channel = domain.get('channel', '')
    packages = domain.get('packages', [])

    # Build class summary for the prompt
    class_summaries = []
    for cls in classes[:80]:  # Limit to avoid token overflow
        summary = {
            'name': cls.get('name', ''),
            'type': cls.get('class_type', ''),
            'package': cls.get('package', ''),
            'stereotype': cls.get('spring_stereotype', ''),
            'extends': cls.get('extends', ''),
            'implements': cls.get('implements', []),
            'fields': [
                {'name': f['name'], 'type': f['type_name'],
                 'annotations': [a['name'] for a in f.get('annotations', [])]}
                for f in cls.get('fields', [])[:20]
            ],
            'methods': [
                {'name': m['name'], 'return': m.get('return_type', ''),
                 'params': m.get('parameters', ''),
                 'annotations': [a['name'] for a in m.get('annotations', [])]}
                for m in cls.get('methods', [])[:30]
            ],
        }
        if cls.get('settings_refs'):
            summary['settings'] = [
                {'key': s['setting_key'], 'default': s.get('default_value', '')}
                for s in cls['settings_refs'][:10]
            ]
        if cls.get('request_mappings'):
            summary['endpoints'] = cls['request_mappings']
        class_summaries.append(summary)

    prompt = f"""You are analyzing a Java/Spring Boot domain for documentation.
All data below is extracted from actual source code by a deterministic parser.

## Domain: {domain_name}
{"Channel: " + channel if channel else ""}
Packages: {', '.join(packages[:10])}
Classes: {domain.get('class_count', 0)}

## Classes Structure
```json
{json.dumps(class_summaries, indent=1, ensure_ascii=False)[:12000]}
```

## Task
Write a comprehensive domain overview in Markdown covering:

1. **Purpose** — What does this domain do? What business problem does it solve?
2. **Architecture** — How are classes organized? What layers/patterns are used?
3. **Data Flow** — How does data flow through this domain? Key entry points → processing → output
4. **Key Classes** — Which classes are the most important and why?
5. **Dependencies** — What external services/DAOs does this domain rely on?
6. **Configuration** — What settings control behavior? How do they branch the logic?
7. **API Endpoints** (if any) — What REST endpoints does this domain expose?

Rules:
- Use ONLY class/method/field names from the data above. Never invent names.
- Be specific about the business logic, not generic Spring descriptions.
- Include Mermaid sequence or flow diagrams where helpful.
- Write in English.
- 500-2000 words depending on domain complexity.
"""
    return prompt


def enrich_domain(
    client,
    model: str,
    domain: dict,
    classes: List[dict],
    fallback_model: str = "",
) -> Optional[str]:
    """
    Enrich a single domain with LLM-generated content.
    Returns the generated Markdown text, or None on failure.
    """
    prompt = build_enrichment_prompt(domain, classes)

    models_to_try = [model]
    if fallback_model and fallback_model != model:
        models_to_try.append(fallback_model)

    for m in models_to_try:
        try:
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": "You are a senior Java architect writing technical documentation. Be precise, use only the data provided. Write in Markdown."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
            )
            return response.choices[0].message.content
        except Exception as e:
            log.warning(f"LLM call failed for model {m}: {e}")
            continue

    return None


def inject_enrichment(domain_page_path: str, enriched_content: str) -> bool:
    """
    Replace the placeholder in domain page with enriched content.
    """
    if not os.path.exists(domain_page_path):
        return False

    with open(domain_page_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if '<!-- LLM_ENRICHMENT_PLACEHOLDER -->' in content:
        replacement = enriched_content
        content = content.replace(
            '<!-- LLM_ENRICHMENT_PLACEHOLDER -->\n\n*This section will be filled by LLM enrichment.*',
            replacement
        )
        # Update status
        content = content.replace('status: parsed', 'status: enriched')

        with open(domain_page_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    else:
        # Already enriched or no placeholder — append
        with open(domain_page_path, 'a', encoding='utf-8') as f:
            f.write('\n\n---\n\n')
            f.write(enriched_content)
        return True


def enrich_all_domains(
    domains: List[dict],
    parsed_data: dict,
    output_dir: str,
    api_key: str,
    base_url: str = "https://api.z.ai/api/coding/paas/v4",
    model: str = "openai/glm-5-turbo",
    fallback_model: str = "openai/glm-4.7",
    delay: float = 1.0,
    limit: int = 0,
) -> dict:
    """
    Enrich all domain pages with LLM-generated content.

    Args:
        delay: seconds between API calls
        limit: max domains to enrich (0 = all)
    """
    client = build_llm_client(api_key, base_url)

    # Build class lookup
    class_lookup = {}
    for mod in parsed_data.get('modules', []):
        for cls in mod.get('classes', []):
            key = f"{cls.get('module', '')}:{cls.get('name', '')}"
            class_lookup[key] = cls

    enriched = 0
    failed = 0
    skipped = 0

    for i, domain in enumerate(domains):
        if limit > 0 and enriched >= limit:
            log.info(f"Reached limit of {limit} domains. Stopping.")
            break

        domain_name = domain.get('name', '')
        module = domain.get('module', '')

        # Find domain page path
        safe_name = domain_name.replace('/', '_').replace(' ', '_')
        domain_page_path = os.path.join(output_dir, module, '_domains', f"{safe_name}.md")

        # Skip if already enriched
        if os.path.exists(domain_page_path):
            with open(domain_page_path, 'r') as f:
                if 'status: enriched' in f.read(200):
                    log.info(f"[{i+1}/{len(domains)}] Skip (already enriched): {domain_name}")
                    skipped += 1
                    continue

        # Get classes for this domain
        domain_classes = []
        for cls_name in domain.get('class_names', []):
            key = f"{module}:{cls_name}"
            if key in class_lookup:
                domain_classes.append(class_lookup[key])

        log.info(f"[{i+1}/{len(domains)}] Enriching: {domain_name} "
                 f"({len(domain_classes)} classes)...")

        try:
            content = enrich_domain(
                client, model, domain, domain_classes, fallback_model
            )
            if content:
                inject_enrichment(domain_page_path, content)
                enriched += 1
                log.info(f"  ✅ Enriched: {domain_name}")
            else:
                failed += 1
                log.warning(f"  ❌ No content: {domain_name}")
        except Exception as e:
            failed += 1
            log.error(f"  ❌ Error enriching {domain_name}: {e}")

        if delay > 0:
            time.sleep(delay)

    log.info(f"Enrichment complete: {enriched} enriched, {failed} failed, {skipped} skipped")
    return {
        "enriched": enriched,
        "failed": failed,
        "skipped": skipped,
    }
