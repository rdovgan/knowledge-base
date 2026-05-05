"""
Domain grouper — groups parsed classes into logical domains.

Strategy:
1. Channel-specific packages (bookingcom, airbnb, etc.) → separate channel domains
2. Remaining packages → grouped by common prefix into domains
3. Domains with too many classes (>50) get split by sub-package
4. Domains with too few classes (<3) get merged with siblings
"""

import os
import re
import json
import logging
from typing import List, Dict
from collections import defaultdict

from .models import Domain, CHANNEL_PATTERNS

log = logging.getLogger(__name__)


def detect_channel(package: str) -> str:
    """Detect channel name from package path."""
    pkg_lower = package.lower()
    for pattern, channel in CHANNEL_PATTERNS.items():
        if pattern in pkg_lower:
            return channel
    return ""


def get_module_name(file_path: str, source_roots: dict) -> str:
    """Determine module from file path."""
    for module_name, source_path in source_roots.items():
        if file_path.startswith(source_path):
            return module_name
    return "unknown"


def group_classes_into_domains(
    classes: List[dict],
    module_name: str,
    max_classes_per_domain: int = 50,
    min_classes_per_domain: int = 5,
) -> List[dict]:
    """
    Group parsed classes into domains.

    Returns list of domain dicts (serializable).
    """
    if not classes:
        return []

    # ── Step 1: Group by (module, channel, package_prefix) ──

    # First pass: detect channel for each class
    channel_groups: Dict[str, List[dict]] = defaultdict(list)
    non_channel_groups: Dict[str, List[dict]] = defaultdict(list)

    for cls in classes:
        package = cls.get('package', '')
        file_path = cls.get('file_path', '')
        channel = detect_channel(package) or detect_channel(file_path)

        if channel:
            channel_groups[channel].append(cls)
        else:
            # Group by top-level package (3 segments: com.mybookingpal.xxx)
            parts = package.split('.')
            if len(parts) >= 3:
                prefix = '.'.join(parts[:3])
            else:
                prefix = package
            non_channel_groups[prefix].append(cls)

    # ── Step 2: Build channel domains ──

    domains = []

    for channel, channel_classes in sorted(channel_groups.items()):
        # Sub-group by package within channel if too large
        if len(channel_classes) > max_classes_per_domain:
            # Group by sub-package
            sub_groups: Dict[str, List[dict]] = defaultdict(list)
            for cls in channel_classes:
                pkg = cls.get('package', '')
                # Use 4-segment prefix for sub-grouping
                parts = pkg.split('.')
                if len(parts) >= 4:
                    sub = '.'.join(parts[:4])
                else:
                    sub = pkg
                sub_groups[sub].append(cls)

            for sub_pkg, sub_classes in sorted(sub_groups.items()):
                # Extract meaningful name from package
                parts = sub_pkg.split('.')
                domain_name = f"{channel}_{'_'.join(parts[-2:])}" if len(parts) >= 2 else channel
                domain_name = domain_name.replace('mybookingpal_', '').replace('com_', '')

                packages = sorted(set(c.get('package', '') for c in sub_classes))
                domains.append({
                    'name': domain_name,
                    'module': module_name,
                    'channel': channel,
                    'packages': packages,
                    'class_names': [c.get('name', '') for c in sub_classes],
                    'class_count': len(sub_classes),
                })
        else:
            packages = sorted(set(c.get('package', '') for c in channel_classes))
            domains.append({
                'name': channel,
                'module': module_name,
                'channel': channel,
                'packages': packages,
                'class_names': [c.get('name', '') for c in channel_classes],
                'class_count': len(channel_classes),
            })

    # ── Step 3: Build non-channel domains ──

    for prefix, group_classes in sorted(non_channel_groups.items()):
        if len(group_classes) > max_classes_per_domain:
            # Split by sub-package
            sub_groups: Dict[str, List[dict]] = defaultdict(list)
            for cls in group_classes:
                pkg = cls.get('package', '')
                parts = pkg.split('.')
                # Progressive prefix length
                if len(parts) >= 5:
                    sub = '.'.join(parts[:5])
                elif len(parts) >= 4:
                    sub = '.'.join(parts[:4])
                else:
                    sub = pkg
                sub_groups[sub].append(cls)

            for sub_pkg, sub_classes in sorted(sub_groups.items()):
                parts = sub_pkg.split('.')
                domain_name = '_'.join(parts[-2:]) if len(parts) >= 2 else sub_pkg
                domain_name = domain_name.replace('mybookingpal_', '')

                packages = sorted(set(c.get('package', '') for c in sub_classes))
                domains.append({
                    'name': domain_name,
                    'module': module_name,
                    'channel': '',
                    'packages': packages,
                    'class_names': [c.get('name', '') for c in sub_classes],
                    'class_count': len(sub_classes),
                })
        else:
            parts = prefix.split('.')
            domain_name = parts[-1] if parts else prefix
            domain_name = domain_name.replace('mybookingpal', module_name)

            packages = sorted(set(c.get('package', '') for c in group_classes))
            domains.append({
                'name': domain_name,
                'module': module_name,
                'channel': '',
                'packages': packages,
                'class_names': [c.get('name', '') for c in group_classes],
                'class_count': len(group_classes),
            })

    # ── Step 4: Merge tiny domains ──

    merged = []
    tiny_buffer = []

    for domain in domains:
        if domain['class_count'] < min_classes_per_domain and not domain['channel']:
            tiny_buffer.append(domain)
            if sum(d['class_count'] for d in tiny_buffer) >= min_classes_per_domain:
                # Merge buffer
                all_classes = []
                all_packages = []
                for td in tiny_buffer:
                    all_classes.extend(td['class_names'])
                    all_packages.extend(td['packages'])
                merged.append({
                    'name': f"{module_name}_misc_{len(merged)}",
                    'module': module_name,
                    'channel': '',
                    'packages': sorted(set(all_packages)),
                    'class_names': all_classes,
                    'class_count': len(all_classes),
                })
                tiny_buffer = []
        else:
            if tiny_buffer:
                # Flush tiny buffer
                if sum(d['class_count'] for d in tiny_buffer) > 0:
                    all_classes = []
                    all_packages = []
                    for td in tiny_buffer:
                        all_classes.extend(td['class_names'])
                        all_packages.extend(td['packages'])
                    merged.append({
                        'name': f"{module_name}_misc_{len(merged)}",
                        'module': module_name,
                        'channel': '',
                        'packages': sorted(set(all_packages)),
                        'class_names': all_classes,
                        'class_count': len(all_classes),
                    })
                tiny_buffer = []
            merged.append(domain)

    # Flush remaining tiny buffer
    if tiny_buffer:
        all_classes = []
        all_packages = []
        for td in tiny_buffer:
            all_classes.extend(td['class_names'])
            all_packages.extend(td['packages'])
        merged.append({
            'name': f"{module_name}_misc_{len(merged)}",
            'module': module_name,
            'channel': '',
            'packages': sorted(set(all_packages)),
            'class_names': all_classes,
            'class_count': len(all_classes),
        })

    return merged


def group_all_modules(parsed_data: dict) -> List[dict]:
    """
    Group all parsed modules into domains.

    parsed_data: dict from load_parsed or parse_module
    Returns: list of domain dicts
    """
    all_domains = []

    # Group per module (channel grouping is module-specific)
    for module_data in parsed_data.get('modules', []):
        module_name = module_data['module']
        classes = module_data.get('classes', [])

        module_domains = group_classes_into_domains(classes, module_name)
        all_domains.extend(module_domains)

        log.info(f"Module {module_name}: {len(classes)} classes → {len(module_domains)} domains")

    # Attach settings maps to domains
    settings_index = build_settings_index(parsed_data)
    for domain in all_domains:
        domain_settings = {}
        for cls_name in domain.get('class_names', []):
            if cls_name in settings_index:
                for sref in settings_index[cls_name]:
                    key = sref['setting_key']
                    if key not in domain_settings:
                        domain_settings[key] = []
                    domain_settings[key].append(sref)
        domain['settings_map'] = domain_settings

    return all_domains


def build_settings_index(parsed_data: dict) -> Dict[str, List[dict]]:
    """Build index: class_name → list of settings refs."""
    index = {}
    for module_data in parsed_data.get('modules', []):
        for cls in module_data.get('classes', []):
            name = cls.get('name', '')
            refs = cls.get('settings_refs', [])
            if refs:
                index[name] = refs
    return index
