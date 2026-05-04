"""
Module Decomposer — splits large modules into manageable domains.

For modules with >200 Java files, instead of one massive exploration,
we identify top-level domains (packages) and treat each as a mini-module.

Strategy:
  - Small modules (<200 files): explore as-is → one set of pages
  - Large modules (200-2000 files): split by top-level packages → domains
  - Huge modules (>2000 files like mbp): split by top-level packages,
    each becomes a sub-module with its own exploration
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SOURCE_ROOT = Path("/home/r.dovgan/mbp-rag")
OUTPUT_ROOT = Path("/home/r.dovgan/cakb/rag")

# Thresholds
SMALL_THRESHOLD = 200    # explore as-is
LARGE_THRESHOLD = 500    # split into domains
HUGE_THRESHOLD = 2000   # split into sub-modules


def count_java_files(path: str) -> int:
    """Count Java files in a directory."""
    result = subprocess.run(
        ['find', path, '-name', '*.java',
         '-not', '-path', '*/.git/*',
         '-not', '-path', '*/target/*'],
        capture_output=True, text=True, timeout=30
    )
    return len([f for f in result.stdout.strip().split('\n') if f])


def _scan_all_java_files(path: str) -> list[str]:
    """Single find call to get all Java files. Cached-friendly."""
    result = subprocess.run(
        ['find', path, '-name', '*.java', '-type', 'f',
         '-not', '-path', '*/.git/*',
         '-not', '-path', '*/target/*'],
        capture_output=True, text=True, timeout=60
    )
    return [f for f in result.stdout.strip().split('\n') if f]


def find_java_packages(path: str) -> list[str]:
    """Find all directories containing .java files."""
    result = subprocess.run(
        ['find', path, '-name', '*.java',
         '-not', '-path', '*/.git/*',
         '-not', '-path', '*/target/*'],
        capture_output=True, text=True
    )
    files = [f for f in result.stdout.strip().split('\n') if f]

    # Get unique directories
    dirs = set()
    for f in files:
        dirs.add(str(Path(f).parent))
    return sorted(dirs)


def get_top_level_domains(source_path: str) -> list[dict]:
    """
    Identify top-level domains by looking at the package structure.
    Uses a single find call instead of per-directory subprocess.
    """
    # Single find call for all Java files
    all_files = _scan_all_java_files(source_path)
    if not all_files:
        return []

    # Find the Java source root
    java_root = source_path
    for candidate in [
        os.path.join(source_path, 'src/main/java'),
        os.path.join(source_path, 'src'),
    ]:
        if os.path.isdir(candidate):
            java_root = candidate
            break

    # Group files by first meaningful package level
    # e.g., com/mybookingpal/{controller,service,dao,...}
    # Find branching point: directory with 5+ subdirs containing .java files
    dir_children = {}  # parent -> set of direct child dirs
    for f in all_files:
        p = Path(f)
        # Walk up to find parents under java_root
        parts = p.relative_to(java_root).parts if str(p).startswith(java_root) else p.parts[-4:]
        for i in range(len(parts)):
            parent = java_root + '/' + '/'.join(parts[:i]) if i > 0 else java_root
            child_name = parts[i] if i < len(parts) - 1 else None
            if child_name:
                dir_children.setdefault(parent, set()).add(child_name)

    # Find branching point (first dir with 5+ children)
    branching_point = None
    for d in sorted(dir_children.keys(), key=len):
        if len(dir_children[d]) >= 5:
            branching_point = d
            break

    if not branching_point:
        branching_point = java_root

    # Get domains = direct children of branching point
    children_names = dir_children.get(branching_point, set())
    domains = []
    for name in sorted(children_names):
        child_path = os.path.join(branching_point, name)
        if not os.path.isdir(child_path):
            continue
        # Count files under this child (from already-scanned list)
        prefix = child_path + '/'
        file_count = len([f for f in all_files if f.startswith(prefix)])
        if file_count > 0:
            domains.append({
                "name": name,
                "path": child_path,
                "file_count": file_count,
                "description": f"Package: {name}",
            })

    return domains


def decompose_module(module_name: str, source_path: str) -> dict:
    """
    Analyze a module and return a decomposition plan.

    Returns:
        {
            "strategy": "direct" | "domain-split" | "sub-module-split",
            "module_name": str,
            "total_files": int,
            "domains": [
                {
                    "name": str,
                    "source_path": str,
                    "output_path": str,
                    "file_count": int,
                    "description": str,
                }
            ]
        }
    """
    total_files = count_java_files(source_path)
    log.info(f"[Decomposer] {module_name}: {total_files} Java files")

    # Small module — explore directly
    if total_files <= SMALL_THRESHOLD:
        log.info(f"[Decomposer] {module_name}: small module, direct exploration")
        return {
            "strategy": "direct",
            "module_name": module_name,
            "total_files": total_files,
            "domains": [{
                "name": module_name,
                "source_path": source_path,
                "output_path": str(OUTPUT_ROOT / module_name),
                "file_count": total_files,
                "description": "entire module",
            }]
        }

    # Large/huge module — split by top-level domains
    raw_domains = get_top_level_domains(source_path)

    if not raw_domains:
        log.info(f"[Decomposer] {module_name}: no domains found, direct exploration")
        return {
            "strategy": "direct",
            "module_name": module_name,
            "total_files": total_files,
            "domains": [{
                "name": module_name,
                "source_path": source_path,
                "output_path": str(OUTPUT_ROOT / module_name),
                "file_count": total_files,
                "description": "entire module",
            }]
        }

    # Recursively split domains that are still too large
    domains = _split_large_domains(raw_domains, module_name, max_depth=3)

    # Merge tiny domains (<30 files) to reduce page count
    domains = _merge_small_domains(domains, min_files=30)

    strategy = "sub-module-split" if total_files > HUGE_THRESHOLD else "domain-split"
    log.info(f"[Decomposer] {module_name}: {strategy} into {len(domains)} domains")
    for d in domains:
        log.info(f"  {d['name']}: {d['file_count']} files")

    return {
        "strategy": strategy,
        "module_name": module_name,
        "total_files": total_files,
        "domains": domains,
    }


def _split_large_domains(raw_domains: list, module_name: str,
                          max_depth: int = 3, prefix: str = "",
                          all_files: list = None) -> list:
    """Recursively split domains that exceed the large threshold."""
    result = []
    for d in raw_domains:
        name = f"{prefix}{d['name']}" if prefix else d["name"]

        if d["file_count"] > LARGE_THRESHOLD and max_depth > 0:
            # Try to split further
            sub_domains = get_top_level_domains(d["path"])
            if sub_domains and len(sub_domains) > 1:
                split = _split_large_domains(
                    sub_domains, module_name, max_depth - 1,
                    prefix=f"{name}-", all_files=all_files
                )
                result.extend(split)
                continue

        result.append({
            "name": name,
            "source_path": d["path"],
            "output_path": str(OUTPUT_ROOT / module_name),
            "file_count": d["file_count"],
            "description": d.get("description", name),
        })
    return result


def _merge_small_domains(domains: list, min_files: int = 30) -> list:
    """
    Merge tiny domains (<min_files) into their parent group.
    e.g., com-rest-wildduck (1 file) + com-rest-thirdhome (1 file)
    → com-rest-other (2 files, combined path)
    """
    large = [d for d in domains if d["file_count"] >= min_files]
    small = [d for d in domains if d["file_count"] < min_files]

    if not small:
        return domains

    # Group small domains by their parent prefix (e.g., "com-rest")
    groups = {}
    for d in small:
        # Extract parent prefix
        parts = d["name"].rsplit("-", 1)
        parent = parts[0] if len(parts) > 1 else "misc"
        groups.setdefault(parent, []).append(d)

    for parent, group in groups.items():
        if len(group) == 1:
            # Only one small domain — keep as-is but bump to min size
            large.append(group[0])
            continue

        # Merge into one domain
        merged_name = f"{parent}-other"
        merged_files = sum(d["file_count"] for d in group)
        # Use first domain's path as base (agent will use FileReadTool for others)
        merged_path = group[0]["source_path"]

        large.append({
            "name": merged_name,
            "source_path": merged_path,
            "output_path": group[0]["output_path"],
            "file_count": merged_files,
            "description": f"Merged {len(group)} small packages under {parent}",
        })

    return large
