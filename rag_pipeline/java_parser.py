"""
Deterministic Java parser — extracts structure without LLM.

Parses .java files using regex to extract:
- Package, imports, class declarations
- Annotations, Spring stereotypes
- Fields, methods, interfaces
- Settings references (@Value, static config constants)
- Branching logic patterns (if/switch on config fields)

Does NOT parse method bodies fully — only looks for condition patterns.
"""

import os
import re
import json
import logging
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import (
    ParsedClass, Annotation, Field, Method,
    SettingsRef, BranchingLogic
)

log = logging.getLogger(__name__)

# ── Regex patterns ────────────────────────────────────────────────

RE_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)
RE_IMPORTS = re.compile(r'^\s*import\s+(?:static\s+)?([\w.*]+)\s*;', re.MULTILINE)

RE_TYPE_DECL = re.compile(
    r'(?:^|(?<=\n))'
    r'[\s]*'
    r'(?:(?:public|protected|private)\s+)?'
    r'(?:abstract\s+)?'
    r'(?:final\s+)?'
    r'(class|interface|enum|@interface)\s+'
    r'(\w+)'
    r'(?:\s*<[^{]*?>)?'
    r'(?:\s+extends\s+([\w.<>,\s?]+?))?'
    r'(?:\s+implements\s+([\w.<>,\s?]+?))?'
    r'\s*\{',
    re.MULTILINE
)

RE_JAVADOC = re.compile(
    r'/\*\*(.*?)\*/',
    re.DOTALL
)

# Field: access_modifier [static] [final] Type name [= value];
RE_FIELD = re.compile(
    r'^[\s]*(?:(private|protected|public)\s+)'
    r'(?:static\s+)?(?:final\s+)?(?:transient\s+)?(?:volatile\s+)?'
    r'([\w<>\[\],\s.]+?)\s+'
    r'(\w+)\s*(?:=|;)',
    re.MULTILINE
)

# Method: [access] [static] ReturnType name(params) [throws ...] {
RE_METHOD = re.compile(
    r'^[\s]*(?:(?:public|protected|private)\s+)?'
    r'(?:static\s+)?(?:final\s+)?(?:abstract\s+)?(?:synchronized\s+)?'
    r'(?:([\w<>\[\],\s.?]+)\s+)?'
    r'(\w+)\s*\(([^)]*)\)\s*'
    r'(?:throws\s+[\w.,\s]+\s*)?'
    r'[{;]',
    re.MULTILINE
)

# @Value("${key}") or @Value("${key:default}")
RE_VALUE_ANNOTATION = re.compile(
    r'@Value\s*\(\s*["\']\$\{([^}:]+)(?::([^}"\']*))?\}["\']\s*\)'
)

# Static config constant: private static final String SETTING = "bp.something";
RE_CONFIG_CONSTANT = re.compile(
    r'private\s+static\s+final\s+(?:String|boolean|int|Integer|Boolean)\s+(\w+)\s*=\s*["\']?([^;"\']+?)["\']?\s*;',
    re.MULTILINE
)

# razorConfig.getString("key") or razorConfig.getBoolean("key")
RE_CONFIG_GETTER = re.compile(
    r'(?:razorConfig|config|configuration)\s*\.\s*(?:getString|getBoolean|getInt|getLong|getDouble|getProperty)\s*\(\s*["\']([^"\']+)["\']\s*(?:,\s*["\']?([^)"\']*)["\']?\s*)?\)'
)

# Request mapping annotations
RE_REQUEST_MAPPING = re.compile(
    r'@(?:RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?["\']([^"\']+)["\']',
    re.MULTILINE
)

# @Autowired field
RE_AUTOWIRED = re.compile(r'@Autowired')

# Spring stereotypes
SPRING_STEREOTYPES = {
    '@Service', '@Component', '@Repository', '@Controller',
    '@RestController', '@Configuration', '@Bean',
    '@RestController', '@ControllerAdvice',
}

# Condition patterns in method bodies (for settings tracking)
RE_IF_FIELD = re.compile(
    r'(?:if|while)\s*\(\s*(!?\s*(?:this\.)?(\w+))\s*(?:!=|==|>|<|\snull|\strue|\sfalse)',
    re.MULTILINE
)
RE_SWITCH_FIELD = re.compile(
    r'switch\s*\(\s*(?:this\.)?(\w+)\s*\)',
    re.MULTILINE
)
RE_TERNARY_FIELD = re.compile(
    r'(\w+)\s*\?\s*.+?\s*:\s*.+?;',
    re.MULTILINE
)


# ── Helpers ───────────────────────────────────────────────────────

def strip_comments(content: str) -> str:
    """Remove Java comments but preserve line numbers."""
    # Block comments (including Javadoc) → preserve newlines
    def replace_block(m):
        return '\n' * m.group().count('\n')
    result = re.sub(r'/\*.*?\*/', replace_block, content, flags=re.DOTALL)
    # Line comments
    result = re.sub(r'//.*$', '', result, flags=re.MULTILINE)
    return result


def strip_strings(content: str) -> str:
    """Replace string literals with placeholders to avoid false matches."""
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', content)


def extract_javadoc_before(content: str, pos: int) -> str:
    """Extract Javadoc comment that appears before a position."""
    # Look backwards from pos for a */ ... /** pattern
    before = content[:pos].rstrip()
    if before.endswith('*/'):
        end = before.rfind('/**')
        if end >= 0:
            comment = content[end:pos].strip()
            # Clean up Javadoc
            lines = comment.split('\n')
            cleaned = []
            for line in lines:
                line = line.strip().lstrip('* ').rstrip()
                if line and not line.startswith('/**') and not line.startswith('*/'):
                    cleaned.append(line)
            return '\n'.join(cleaned)
    return ""


def find_annotation_block(content: str, before_pos: int) -> List[Annotation]:
    """Extract annotations that appear right before a position."""
    annotations = []
    # Get lines before the position
    before = content[:before_pos].rstrip()

    # Find annotations: @Name or @Name(params)
    # Work backwards from the declaration
    lines = before.split('\n')
    i = len(lines) - 1
    while i >= 0:
        line = lines[i].strip()
        if not line:
            break
        # Check if this is an annotation
        m = re.match(r'@(\w+)(?:\s*\((.+)\))?$', line)
        if m:
            annotations.insert(0, Annotation(name=m.group(1), params=m.group(2) or ""))
            i -= 1
            continue
        # Multi-line annotation — keep going
        if line.startswith('@'):
            annotations.insert(0, Annotation(name=line.lstrip('@').split('(')[0].strip(), params=""))
            i -= 1
            continue
        break

    return annotations


def find_matching_brace(content: str, start: int) -> int:
    """Find the position of the matching closing brace."""
    depth = 0
    i = start
    end = len(content)
    while i < end:
        ch = content[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        elif ch == '"':
            # Skip string literal
            i += 1
            while i < end and content[i] != '"':
                if content[i] == '\\':
                    i += 1
                i += 1
        elif ch == "'":
            i += 1
            while i < end and content[i] != "'":
                if content[i] == '\\':
                    i += 1
                i += 1
        i += 1
    return end - 1


# ── Main parser ───────────────────────────────────────────────────

def parse_java_file(file_path: str, module_name: str) -> List[ParsedClass]:
    """Parse a single Java file. Returns list of ParsedClass (may include inner classes)."""
    # Skip large generated files (OTA models, JAXB stubs)
    file_size = os.path.getsize(file_path)
    if file_size > 200_000:  # >200KB — likely generated
        return []

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        log.warning(f"Cannot read {file_path}: {e}")
        return []

    clean = strip_comments(content)
    package_match = RE_PACKAGE.search(clean)
    package = package_match.group(1) if package_match else ""
    imports = [m.group(1) for m in RE_IMPORTS.finditer(clean)]

    results = []

    for match in RE_TYPE_DECL.finditer(clean):
        class_type_raw = match.group(1)
        class_name = match.group(2)
        extends_raw = match.group(3)
        implements_raw = match.group(4)

        class_type = class_type_raw if class_type_raw != '@interface' else 'annotation'
        extends = extends_raw.strip() if extends_raw else ""
        implements = [s.strip() for s in implements_raw.split(',')] if implements_raw else []

        # Find class body
        brace_start = match.end() - 1  # position of opening {
        brace_end = find_matching_brace(clean, brace_start)
        class_body = clean[brace_start:brace_end + 1]

        # Class-level annotations
        class_annotations = find_annotation_block(clean, match.start())

        # Spring stereotype
        spring_stereotype = ""
        for ann in class_annotations:
            ann_name = f"@{ann.name}"
            if ann_name in SPRING_STEREOTYPES:
                spring_stereotype = ann_name
                break

        # Request mappings (class-level)
        request_mappings = []
        for ann in class_annotations:
            if ann.name in ('RequestMapping', 'GetMapping', 'PostMapping',
                           'PutMapping', 'DeleteMapping', 'PatchMapping'):
                m = re.search(r'["\']([^"\']+)["\']', ann.params)
                if m:
                    request_mappings.append(m.group(1))

        # Javadoc before class
        javadoc = extract_javadoc_before(content, match.start())

        # Parse fields from class body
        fields = []
        # Split body into lines and process annotations + fields together
        body_lines = class_body.split('\n')
        pending_annotations: List[Annotation] = []
        for line in body_lines:
            stripped = line.strip()
            # Annotation
            if stripped.startswith('@'):
                m_ann = re.match(r'@(\w+)(?:\s*\((.+)\))?$', stripped)
                if m_ann:
                    pending_annotations.append(
                        Annotation(name=m_ann.group(1), params=m_ann.group(2) or "")
                    )
                continue
            # Field
            m_field = RE_FIELD.match(line)
            if m_field:
                access, type_name, field_name = m_field.groups()
                fields.append(Field(
                    name=field_name,
                    type_name=type_name.strip(),
                    annotations=list(pending_annotations),
                ))
                pending_annotations = []
                continue
            if stripped and not stripped.startswith('//'):
                pending_annotations = []

        # Parse methods from class body
        methods = []
        method_matches = list(RE_METHOD.finditer(class_body))
        for i, m in enumerate(method_matches):
            ret_type = (m.group(1) or "").strip()
            method_name = m.group(2)
            params = m.group(3) or ""

            # Skip if it looks like a field (constructor with no return type)
            if not ret_type and method_name == class_name:
                # Constructor
                ret_type = "constructor"

            # Skip common false positives
            if method_name in ('if', 'while', 'for', 'switch', 'catch', 'return',
                              'new', 'else', 'try', 'throw', 'assert'):
                continue

            # Find method annotations by looking at lines before
            before_pos = m.start()
            method_anns = []
            lines_before = class_body[:before_pos].rstrip().split('\n')
            j = len(lines_before) - 1
            while j >= 0:
                ann_line = lines_before[j].strip()
                if ann_line.startswith('@'):
                    m_a = re.match(r'@(\w+)(?:\s*\((.+)\))?$', ann_line)
                    if m_a:
                        method_anns.insert(0, Annotation(name=m_a.group(1), params=m_a.group(2) or ""))
                    j -= 1
                    continue
                if ann_line:
                    break
                j -= 1

            # Check for request mappings in method annotations
            for ann in method_anns:
                if ann.name in ('RequestMapping', 'GetMapping', 'PostMapping',
                               'PutMapping', 'DeleteMapping', 'PatchMapping'):
                    rm = re.search(r'["\']([^"\']+)["\']', ann.params)
                    if rm:
                        request_mappings.append(rm.group(1))

            methods.append(Method(
                name=method_name,
                return_type=ret_type,
                parameters=params.strip(),
                annotations=method_anns,
                line=m.start(),
            ))

        # ── Settings extraction ──────────────────────────────

        settings_refs: List[SettingsRef] = []

        # 1. @Value annotations on fields
        for vmatch in RE_VALUE_ANNOTATION.finditer(class_body):
            key = vmatch.group(1)
            default = vmatch.group(2) or ""
            settings_refs.append(SettingsRef(
                setting_key=key,
                default_value=default,
                source_annotation="@Value",
                context=class_name,
                file_path=file_path,
            ))

        # 2. Static config constants (private static final String X = "bp.y.z")
        for cmatch in RE_CONFIG_CONSTANT.finditer(clean):
            const_name = cmatch.group(1)
            const_val = cmatch.group(2).strip()
            if const_val.startswith('bp.') or const_val.startswith('channel.') or const_val.startswith('spring.'):
                settings_refs.append(SettingsRef(
                    setting_key=const_val,
                    source_annotation="static_final",
                    field_name=const_name,
                    context=class_name,
                    file_path=file_path,
                ))

        # 3. razorConfig.getXxx("key") calls
        for gmatch in RE_CONFIG_GETTER.finditer(class_body):
            key = gmatch.group(1)
            default = gmatch.group(2) or ""
            settings_refs.append(SettingsRef(
                setting_key=key,
                default_value=default,
                source_annotation="razorConfig",
                context=class_name,
                file_path=file_path,
            ))

        # ── Branching logic extraction ───────────────────────

        branching: List[BranchingLogic] = []

        # Build map of @Value fields
        value_fields = {}
        for sref in settings_refs:
            if sref.source_annotation == "@Value" and sref.field_name:
                value_fields[sref.field_name] = sref.setting_key

        # Also track razorConfig getters used in the same class
        config_field_names = set()
        for f in fields:
            for ann in f.annotations:
                if ann.name == 'Autowired' and 'Config' in f.type_name:
                    config_field_names.add(f.name)

        # Look for if/switch on config-related fields
        # For each method, scan its body for condition patterns
        # (simplified: scan whole class body for now)
        for ifmatch in RE_IF_FIELD.finditer(class_body):
            condition_text = ifmatch.group(0).strip()
            field_ref = ifmatch.group(2)
            if field_ref in value_fields:
                branching.append(BranchingLogic(
                    field_name=field_ref,
                    setting_key=value_fields[field_ref],
                    method_name="",  # would need method boundary detection
                    condition_type="if",
                    condition_text=condition_text[:200],
                    file_path=file_path,
                ))

        for swmatch in RE_SWITCH_FIELD.finditer(class_body):
            field_ref = swmatch.group(1)
            if field_ref in value_fields:
                branching.append(BranchingLogic(
                    field_name=field_ref,
                    setting_key=value_fields[field_ref],
                    method_name="",
                    condition_type="switch",
                    condition_text=field_ref,
                    file_path=file_path,
                ))

        parsed = ParsedClass(
            name=class_name,
            class_type=class_type,
            package=package,
            file_path=file_path,
            module=module_name,
            extends=extends,
            implements=implements,
            annotations=class_annotations,
            fields=fields,
            methods=methods,
            imports=imports,
            settings_refs=settings_refs,
            branching_logic=branching,
            javadoc=javadoc,
            spring_stereotype=spring_stereotype,
            request_mappings=request_mappings,
            line_count=content.count('\n') + 1,
        )

        results.append(parsed)

    return results


def parse_properties_file(file_path: str, module_name: str) -> dict:
    """Parse a .properties file."""
    props = {}
    profile = ""
    # Extract profile from path: .../development/application.properties
    parts = file_path.split('/')
    for i, p in enumerate(parts):
        if p == 'resources' and i + 1 < len(parts) and parts[i + 1] not in ('com',):
            profile = parts[i + 1]
            break

    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, _, val = line.partition('=')
                    props[key.strip()] = val.strip()
    except Exception as e:
        log.warning(f"Cannot read {file_path}: {e}")

    return {
        "file_path": file_path,
        "module": module_name,
        "profile": profile,
        "properties": props,
    }


def parse_mapper_xml(file_path: str, module_name: str) -> dict:
    """Parse a MyBatis mapper XML file."""
    import xml.etree.ElementTree as ET

    namespace = ""
    statements = []

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        namespace = root.get('namespace', '')

        for stmt in root:
            tag = stmt.tag
            if tag in ('select', 'insert', 'update', 'delete', 'sql'):
                sid = stmt.get('id', '')
                param_type = stmt.get('parameterType', '')
                result_type = stmt.get('resultType', '') or stmt.get('resultMap', '')
                text = (stmt.text or '').strip()[:500]
                statements.append({
                    "type": tag,
                    "id": sid,
                    "parameter_type": param_type,
                    "result_type": result_type,
                    "sql_preview": text,
                })
    except Exception as e:
        log.warning(f"Cannot parse mapper XML {file_path}: {e}")

    return {
        "file_path": file_path,
        "module": module_name,
        "namespace": namespace,
        "statements": statements,
    }


# ── Batch processing ──────────────────────────────────────────────

def _parse_java_file(args):
    """Worker for Java files (process-safe)."""
    file_path, module_name = args
    try:
        results = parse_java_file(file_path, module_name)
        return ("java", [r.to_dict() for r in results])
    except Exception as e:
        return ("error", str(e))


def _parse_other_file(args):
    """Parse a non-Java file (properties or mapper XML)."""
    file_path, module_name = args
    ext = file_path.rsplit('.', 1)[-1]
    if ext == 'properties':
        return ("properties", parse_properties_file(file_path, module_name))
    elif ext == 'xml':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                first = f.read(500)
            if 'mybatis.org' in first or '<mapper' in first:
                return ("mapper", parse_mapper_xml(file_path, module_name))
        except:
            pass
    return None


def parse_module(source_path: str, module_name: str) -> dict:
    """Parse all source files in a module."""
    java_files = []
    properties_files = []
    xml_files = []

    for root, dirs, files in os.walk(source_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('target', 'build', 'node_modules')]
        for f in files:
            fp = os.path.join(root, f)
            if f.endswith('.java'):
                if '/test/' not in fp and '/Test' not in f:
                    java_files.append(fp)
            elif f.endswith('.properties'):
                properties_files.append(fp)
            elif f.endswith('.xml') and '/resources/' in fp:
                xml_files.append(fp)

    log.info(f"Module {module_name}: {len(java_files)} Java, "
             f"{len(properties_files)} properties, {len(xml_files)} XML")

    classes = []
    properties_list = []
    mappers = []
    errors = 0

    # ── Parse Java files with ThreadPoolExecutor (avoids pickling issues) ──
    from concurrent.futures import ThreadPoolExecutor, as_completed

    java_tasks = [(f, module_name) for f in java_files]
    workers = min(os.cpu_count() or 4, 8)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_parse_java_file, t): t for t in java_tasks}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 1000 == 0:
                log.info(f"  Parsed {done}/{len(java_tasks)} Java files...")
            try:
                result = future.result()
                if result is None:
                    continue
                kind, data = result
                if kind == "java":
                    classes.extend(data)
                else:
                    errors += 1
            except Exception as e:
                errors += 1

    # ── Parse properties and XML files sequentially (small count) ──
    for f in properties_files:
        result = _parse_other_file((f, module_name))
        if result and result[0] == "properties":
            properties_list.append(result[1])

    for f in xml_files:
        result = _parse_other_file((f, module_name))
        if result and result[0] == "mapper":
            mappers.append(result[1])

    if errors:
        log.warning(f"  {errors} files had parse errors")

    return {
        "module": module_name,
        "source_path": source_path,
        "classes": classes,
        "properties": properties_list,
        "mappers": mappers,
        "stats": {
            "java_files": len(java_files),
            "classes_parsed": len(classes),
            "properties_files": len(properties_list),
            "mapper_files": len(mappers),
            "errors": errors,
        }
    }
