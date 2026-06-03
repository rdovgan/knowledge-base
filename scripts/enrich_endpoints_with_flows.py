#!/usr/bin/env python3
"""
Enrich endpoint wiki pages with per-endpoint business flow descriptions.

For each endpoint method in a controller:
1. Parse the controller method body to find delegation calls
2. Trace into the target service/api class (2 levels deep)
3. Extract all service calls, DAO calls, MyBatis mapper calls
4. Generate per-endpoint flow description with business logic

Usage:
    python3 enrich_endpoints_with_flows.py [--dry-run] [--controller Name] [--endpoints-dir DIR]
"""

import os
import re
import sys
import argparse
from typing import List, Dict, Optional, Tuple, Set
from collections import OrderedDict
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────

SOURCE_ROOT = "/home/r.dovgan/mbp-rag/mbp/src"
ENDPOINTS_DIR = "/home/r.dovgan/cakb/rag/mbp/_endpoints"
WIKI_ROOT = "/home/r.dovgan/cakb/rag/mbp"

# ── Noise words to skip in call extraction ─────────────────────
SKIP_OBJECTS = frozenset({
    'LOG', 'log', 'this', 'super', 'Arrays', 'Collections', 'Collectors',
    'String', 'Integer', 'Long', 'NumberUtils', 'StringUtils',
    'CalendarUtil', 'DateUtils', 'Base64Utils', 'CollectionUtils',
    'Objects', 'LocalDate', 'LocalDateTime', 'Calendar', 'Date',
    'Stream', 'Math', 'Response', 'Model', 'RazorServer',
    'EventLogManager', 'EventType', 'ExecutionState',
    'SupplierApiUtils', 'ResponseUtil', 'LogsUtil', 'LogApiUtils',
    'CommonDateUtils', 'ImageUtils', 'FeeUtils', 'ProductUtils',
    'CustomerUtils', 'PaymentHelper', 'CommonContentUtils',
    'ReservationMappingUtils', 'ChannelConfigurationUtils',
    'HttpHeaders', 'MediaType', 'ResponseEntity', 'BookingPalEnums',
    'Map', 'List', 'Set', 'HashMap', 'ArrayList', 'TreeMap', 'ConcurrentHashMap',
    'Optional', 'Queue', 'AtomicBoolean', 'AtomicReference',
    'Arrays', 'System', 'out', 'Arrays',
    'Path', 'Paths', 'File', 'Files', 'InputStream', 'ByteArrayOutputStream',
    'Class', 'Thread', 'XSSFWorkbook', 'Sheet', 'Row', 'Cell', 'CellStyle',
    'DataFormat', 'HorizontalAlign', 'VerticalAlign',
    'Base64', 'StandardCharsets', 'Charsets',
    'HttpStatus', 'LoggerFactory', 'Logger',
    # Enum/constant noise
    'ExecutionState', 'EventType', 'State', 'Final', 'Cancelled', 'Confirmed',
    'ReservationConstants', 'State', 'BPCommissionName',
    'Boolean', 'Byte', 'Short', 'Float', 'Double', 'Character', 'Void',
})

SKIP_METHODS = frozenset({
    'get', 'set', 'toString', 'equals', 'hashCode', 'valueOf',
    'getInstance', 'openSession', 'build', 'ok', 'add', 'put',
    'size', 'stream', 'collect', 'map', 'filter', 'forEach',
    'format', 'println', 'encode', 'parse', 'strip', 'trim',
    'contains', 'isEmpty', 'isNotEmpty', 'length', 'startsWith', 'endsWith',
    'close', 'flush', 'write', 'read', 'skip', 'iterator',
    'next', 'hasNext', 'keySet', 'values', 'entrySet',
    'getClass', 'getName', 'getSimpleName', 'getMessage', 'getCause',
    'toArray', 'asList', 'copyOf', 'sort', 'reverse',
    'abs', 'max', 'min', 'ceil', 'floor',
    'assertTrue', 'assertFalse', 'assertNotNull',
    'autoSizeColumn', 'createRow', 'createCell', 'setCellValue', 'setCellStyle',
    'createSheet', 'createCellStyle', 'createDataFormat',
    'compareTo', 'append', 'indexOf', 'substring', 'replace', 'toLowerCase', 'toUpperCase',
    'orElse', 'isPresent', 'ifPresent', 'getAndAdd', 'set',
})

# ── Java File Cache ────────────────────────────────────────────
_java_cache: Dict[str, Optional[str]] = {}

def read_java_file(class_name: str) -> Optional[str]:
    """Find and read a Java source file by class name (cached)."""
    if class_name in _java_cache:
        return _java_cache[class_name]
    for root, dirs, files in os.walk(SOURCE_ROOT):
        dirs[:] = [d for d in dirs if d not in ('test', 'tests')]
        for f in files:
            if f == f"{class_name}.java":
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
                    _java_cache[class_name] = content
                    return content
    _java_cache[class_name] = None
    return None


# ── Java Parsing ───────────────────────────────────────────────

def extract_imports(content: str) -> Dict[str, str]:
    """Extract class→package mapping from imports."""
    imports = {}
    for match in re.finditer(r'import\s+(?:static\s+)?([\w.]+)\s*;', content):
        full = match.group(1)
        parts = full.rsplit('.', 1)
        if len(parts) == 2:
            imports[parts[1]] = parts[0]
    return imports


def extract_fields(content: str) -> Dict[str, str]:
    """Extract field name→type mapping (simple type name)."""
    fields = {}
    for match in re.finditer(
        r'(?:private|protected|public)\s+(?:static\s+)?(?:final\s+)?'
        r'([\w<>\[\],\s.]+?)\s+(\w+)\s*(?:=|;)',
        content, re.MULTILINE
    ):
        type_name = match.group(1).strip()
        field_name = match.group(2)
        # Get simple class name
        simple = type_name.split('.')[-1].strip()
        simple = re.sub(r'<.*>', '', simple).strip()
        if field_name.startswith('LOG') or simple in ('Logger', 'boolean', 'int', 'Integer', 'double', 'String', 'long'):
            continue
        fields[field_name] = simple
    return fields


def find_brace_end(content: str, start: int) -> int:
    """Find closing brace matching opening brace at start position."""
    depth = 0
    i = start
    in_string = False
    string_char = None
    while i < len(content):
        ch = content[i]
        if in_string:
            if ch == '\\':
                i += 2
                continue
            if ch == string_char:
                in_string = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            string_char = ch
        elif ch == '/' and i + 1 < len(content):
            if content[i+1] == '/':
                nl = content.find('\n', i)
                i = nl + 1 if nl != -1 else len(content)
                continue
            elif content[i+1] == '*':
                end_comment = content.find('*/', i + 2)
                i = end_comment + 2 if end_comment != -1 else len(content)
                continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(content)


def extract_method_body(class_body: str, method_name: str) -> Optional[str]:
    """Extract method body text."""
    # Find method declarations
    candidates = []
    for match in re.finditer(
        rf'(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?'
        rf'(?:[\w<>\[\],\s.+]+?)\s+{re.escape(method_name)}\s*\(',
        class_body
    ):
        # Find opening brace
        rest = class_body[match.end():]
        paren_end = 0
        depth = 1
        for i, ch in enumerate(rest):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    paren_end = i
                    break
        after_params = rest[paren_end + 1:]
        # Skip throws clause
        brace_pos = after_params.find('{')
        if brace_pos == -1 or brace_pos > 200:
            continue  # abstract/interface or annotation
        # Also check it's not followed by ; (annotation method)
        semi_pos = after_params.find(';')
        if semi_pos != -1 and semi_pos < brace_pos:
            continue
        actual_brace = match.end() + paren_end + 1 + brace_pos
        end = find_brace_end(class_body, actual_brace)
        body = class_body[actual_brace + 1:end].strip()
        candidates.append(body)

    if candidates:
        return candidates[0]  # Return first match
    return None


def extract_endpoint_methods(content: str) -> List[Dict]:
    """Extract all JAX-RS endpoint methods from a controller."""
    methods = []

    # Find all positions of HTTP method annotations
    for hm in re.finditer(r'@(GET|POST|PUT|DELETE|PATCH)\b', content):
        http_verb = hm.group(1)
        pos = hm.end()

        # Look backward for @Path annotation (within 500 chars)
        pre_window = content[max(0, hm.start() - 500):hm.start()]
        # Also look forward past the annotation for @Path
        post_window = content[pos:pos + 300]

        # Find @Path - could be before or after the HTTP verb annotation
        path_match = re.findall(r'@Path\s*\(\s*"([^"]*)"\s*\)', pre_window)
        if not path_match:
            path_match = re.findall(r'@Path\s*\(\s*"([^"]*)"\s*\)', post_window)
        method_path = path_match[-1] if path_match else ""

        # Description from @Description or @ApiMethod
        desc = ""
        desc_match = re.search(r'@Description\s*\(\s*value\s*=\s*"([^"]*)"', pre_window)
        if not desc_match:
            desc_match = re.search(r'summary\s*=\s*"([^"]*)"', pre_window)
        if not desc_match:
            desc_match = re.search(r'description\s*=\s*"([^"]*)"', pre_window)
        if desc_match:
            desc = desc_match.group(1)

        # Find method declaration after all annotations
        search_text = content[pos:]
        method_match = re.search(
            r'(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?'
            r'([\w<>\[\],\s]+?)\s+(\w+)\s*\(',
            search_text[:800]
        )
        if not method_match:
            continue

        return_type = method_match.group(1).strip()
        method_name = method_match.group(2)

        # Find full params
        abs_start = pos + method_match.start()
        paren_pos = content.index('(', abs_start)
        depth = 1
        ppos = paren_pos + 1
        while ppos < len(content) and depth > 0:
            if content[ppos] == '(':
                depth += 1
            elif content[ppos] == ')':
                depth -= 1
            ppos += 1
        params_str = content[paren_pos + 1:ppos - 1]

        # Parse params
        params = parse_params(params_str)

        # Find EventType after method body
        event_type = ""
        post_method = content[ppos:ppos + 2000]
        for et in re.finditer(r'EventType\.(\w+)', post_method):
            event_type = et.group(1)
            break  # First match

        # Find @Produces / @Consumes
        produces = ""
        consumes = ""
        ann_window = content[max(0, hm.start() - 600):pos + 400]
        prod_match = re.findall(r'@Produces\s*\([^)]*\)', ann_window)
        cons_match = re.findall(r'@Consumes\s*\([^)]*\)', ann_window)

        methods.append({
            'http_method': http_verb,
            'path': method_path,
            'name': method_name,
            'return_type': return_type,
            'params': params,
            'description': desc,
            'event_type': event_type,
        })

    return methods


def parse_params(params_str: str) -> List[Dict]:
    """Parse Java method parameters into structured data."""
    if not params_str.strip():
        return []

    # Split by commas respecting generics and parens
    parts = []
    depth = 0
    current = ""
    for ch in params_str:
        if ch in '<(':
            depth += 1
            current += ch
        elif ch in '>)':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())

    params = []
    for p in parts:
        if not p:
            continue

        # Extract annotations
        annotations = re.findall(r'@(\w+)', p)

        # Remove annotations from the string
        clean = re.sub(r'@\w+(?:\([^)]*\))?\s*', '', p).strip()

        # Split type and name: last word is name, rest is type
        tokens = clean.split()
        if len(tokens) >= 2:
            param_name = tokens[-1]
            param_type = ' '.join(tokens[:-1])
        elif len(tokens) == 1:
            param_name = tokens[0]
            param_type = ""
        else:
            continue

        # Determine source from annotations
        source = "param"
        if 'PathParam' in annotations:
            source = "path"
        elif 'QueryParam' in annotations:
            source = "query"
        elif 'BodyObject' in annotations or 'RequestBody' in annotations:
            source = "body"
        elif 'Context' in annotations:
            source = "context"

        # Skip context params
        if source == "context":
            continue

        # Skip if type is HttpServletRequest etc
        if any(t in param_type for t in ('HttpServletRequest', 'HttpServletResponse', 'MultipartBody')):
            continue

        params.append({
            'name': param_name,
            'type': param_type,
            'annotations': annotations,
            'source': source,
        })

    return params


def extract_calls(body: str, fields: Dict[str, str]) -> List[Dict]:
    """Extract meaningful service/DAO/mapper calls from a method body."""
    calls = []
    seen = set()

    for match in re.finditer(r'(\w+)\.(\w+)\s*\(', body):
        obj = match.group(1)
        method = match.group(2)

        if obj in SKIP_OBJECTS or method in SKIP_METHODS:
            continue

        # Skip enum constants (ALL_CAPS with underscores)
        if re.match(r'^[A-Z][A-Z0-9_]+$', obj) and '_' in obj:
            continue
        # Skip likely enum values (PascalCase single words that aren't service classes)
        if re.match(r'^[A-Z][a-z]+$', obj) and method in ('name', 'ordinal', 'values', 'toString'):
            continue

        # Deduplicate same object.method calls
        key = f"{obj}.{method}"
        if key in seen:
            continue
        seen.add(key)

        # Determine type
        service_class = ""
        if obj in fields:
            service_class = fields[obj]
            call_type = "service"
        elif obj[0].isupper():
            service_class = obj
            call_type = "static"
        else:
            call_type = "local"

        calls.append({
            'object': obj,
            'method': method,
            'type': call_type,
            'service_class': service_class,
        })

    return calls


def extract_mapper_calls(body: str) -> List[str]:
    """Extract MyBatis mapper calls like sqlSession.getMapper(XxxMapper.class)."""
    mappers = []
    for match in re.finditer(r'getMapper\s*\(\s*(\w+)\.class', body):
        mappers.append(match.group(1))
    return mappers


def extract_flow_steps(body: str) -> List[str]:
    """Extract high-level business logic steps from a method body."""
    steps = []
    lines = body.split('\n')
    seen = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('//') or stripped.startswith('*') or stripped.startswith('@'):
            continue
        if stripped in ('{', '}', 'try {', '} catch', '} finally', 'else {', '} else {'):
            continue
        if len(stripped) < 5:
            continue

        step = None

        # SqlSession / mapper calls
        if 'sqlSession.getMapper' in stripped:
            mapper = re.search(r'getMapper\s*\(\s*(\w+)', stripped)
            if mapper:
                step = f"Get {mapper.group(1)} (MyBatis mapper)"
        elif 'openSession' in stripped:
            step = "Open database session"

        # try-with-resources SqlSession
        elif re.match(r'try\s*\(\s*SqlSession', stripped):
            step = "Open database session"

        # Request validation
        elif 'requestValidation' in stripped or 'validateRequest' in stripped:
            step = "Validate request"

        # Condition checks (if statements) - extract the condition
        elif re.match(r'if\s*\(', stripped):
            cond = re.sub(r'^if\s*\(\s*', '', stripped)
            cond = re.sub(r'\)\s*\{?\s*$', '', cond)
            # Simplify common patterns
            if '!=' in cond and 'null' in cond:
                var = cond.split('!=')[0].strip()
                step = f"Check {var} is not null"
            elif '==' in cond and 'null' in cond:
                var = cond.split('==')[0].strip()
                step = f"Check {var} is null"
            elif '.isEmpty()' in cond or 'CollectionUtils.isEmpty' in cond:
                step = f"Check collection is empty"
            elif '.isNotEmpty()' in cond or 'CollectionUtils.isNotEmpty' in cond:
                step = f"Check collection is not empty"
            elif '.equalsIgnoreCase(' in cond:
                parts = cond.split('.equalsIgnoreCase')
                if parts:
                    step = f"Check {parts[0].strip()} value"
            elif len(cond) > 10 and len(cond) < 100:
                # Generic condition
                cond_clean = re.sub(r'\s+', ' ', cond).strip()
                step = f"Condition: {cond_clean}"

        # Variable assignments from service calls
        elif '=' in stripped and not stripped.startswith('if') and not stripped.startswith('for') and not stripped.startswith('while'):
            # Assignment with a method call
            rhs = stripped.split('=', 1)[1].strip()
            # Check if it's a significant call
            call_match = re.search(r'(\w+)\.(\w+)\s*\(', rhs)
            if call_match and call_match.group(1) not in SKIP_OBJECTS and call_match.group(2) not in SKIP_METHODS:
                obj = call_match.group(1)
                method = call_match.group(2)
                # Make readable
                action = method_to_verb(method)
                target = obj.replace('Dao', '').replace('Service', '').replace('Mapper', '')
                step = f"{action} {target} via {obj}.{method}()"
            elif 'new ' in rhs:
                # Object creation
                new_match = re.search(r'new\s+(\w+)', rhs)
                if new_match:
                    cls = new_match.group(1)
                    if cls not in ('ArrayList', 'HashMap', 'Response', 'EventLogResponseWrapper',
                                   'RazorResponse', 'StringBuilder'):
                        step = f"Create {cls} instance"

        # Return with error
        elif 'return' in stripped and ('BAD' in stripped or 'Error' in stripped or 'error' in stripped):
            step = "Return error response"
        elif 'return' in stripped and 'OK' in stripped:
            step = "Return success response"

        if step and step not in seen:
            steps.append(step)
            seen.add(step)

    return steps


def method_to_verb(method: str) -> str:
    """Convert a method name to a readable verb."""
    if method.startswith('read'):
        return "Read"
    elif method.startswith('get'):
        return "Get"
    elif method.startswith('find'):
        return "Find"
    elif method.startswith('search'):
        return "Search"
    elif method.startswith('create'):
        return "Create"
    elif method.startswith('update'):
        return "Update"
    elif method.startswith('delete'):
        return "Delete"
    elif method.startswith('cancel'):
        return "Cancel"
    elif method.startswith('import'):
        return "Import"
    elif method.startswith('export'):
        return "Export"
    elif method.startswith('save'):
        return "Save"
    elif method.startswith('validate'):
        return "Validate"
    elif method.startswith('check'):
        return "Check"
    elif method.startswith('fill'):
        return "Fill"
    elif method.startswith('count'):
        return "Count"
    elif method.startswith('add'):
        return "Add"
    elif method.startswith('remove'):
        return "Remove"
    elif method.startswith('process'):
        return "Process"
    elif method.startswith('build'):
        return "Build"
    elif method.startswith('generate'):
        return "Generate"
    else:
        return "Call"


# ── Call Chain Tracing ──────────────────────────────────────────

def trace_endpoint(
    ctrl_source: str,
    ctrl_fields: Dict[str, str],
    ctrl_imports: Dict[str, str],
    endpoint: Dict,
) -> Dict:
    """Trace the full call chain for an endpoint method (2 levels deep)."""
    class_body = extract_class_body(ctrl_source)
    if not class_body:
        return {'services': [], 'daos': [], 'mappers': [], 'steps': [], 'calls': []}

    method_body = extract_method_body(class_body, endpoint['name'])
    if not method_body:
        return {'services': [], 'daos': [], 'mappers': [], 'steps': [], 'calls': []}

    all_services = OrderedDict()
    all_daos = OrderedDict()
    all_mappers = []
    all_steps = []
    all_calls = []

    # Level 0: Controller method
    ctrl_calls = extract_calls(method_body, ctrl_fields)
    ctrl_mappers = extract_mapper_calls(method_body)
    ctrl_steps = extract_flow_steps(method_body)

    for m in ctrl_mappers:
        all_mappers.append(m)

    for c in ctrl_calls:
        all_calls.append((c['object'], c['method']))
        svc = c['service_class']
        if svc:
            # Skip Java stdlib types
            if svc in ('Function', 'Comparator', 'Supplier', 'Consumer', 'Predicate',
                       'Runnable', 'Callable', 'Optional', 'Stream', 'Collectors'):
                continue
            if svc.endswith('Dao') or svc.endswith('DAO'):
                all_daos[svc] = c['object']
            elif svc not in all_services:
                all_services[svc] = c['object']

    all_steps.extend(ctrl_steps)

    # Level 1: Trace into each service call
    for c in ctrl_calls:
        if c['type'] != 'service' or not c['service_class']:
            continue

        svc_name = c['service_class']
        svc_source = read_java_file(svc_name)
        if not svc_source:
            continue

        svc_fields = extract_fields(svc_source)
        svc_imports = extract_imports(svc_source)
        svc_body = extract_class_body(svc_source)
        if not svc_body:
            continue

        svc_method_body = extract_method_body(svc_body, c['method'])
        if not svc_method_body:
            continue

        svc_calls = extract_calls(svc_method_body, svc_fields)
        svc_mappers = extract_mapper_calls(svc_method_body)
        svc_steps = extract_flow_steps(svc_method_body)

        for m in svc_mappers:
            if m not in all_mappers:
                all_mappers.append(m)

        for sc in svc_calls:
            svc = sc['service_class']
            if svc:
                # Skip Java stdlib types
                if svc in ('Function', 'Comparator', 'Supplier', 'Consumer', 'Predicate',
                           'Runnable', 'Callable', 'Optional', 'Stream', 'Collectors'):
                    continue
                if svc.endswith('Dao') or svc.endswith('DAO'):
                    if svc not in all_daos:
                        all_daos[svc] = sc['object']
                elif svc.endswith('Mapper') and 'Mapper' in svc:
                    if svc not in all_mappers:
                        all_mappers.append(svc)
                elif svc not in all_services:
                    all_services[svc] = sc['object']

            # Level 2: Trace one more level
            if sc['type'] == 'service' and svc and not svc.endswith('Dao'):
                deep_source = read_java_file(svc)
                if deep_source:
                    deep_fields = extract_fields(deep_source)
                    deep_body = extract_class_body(deep_source)
                    if deep_body:
                        deep_method = extract_method_body(deep_body, sc['method'])
                        if deep_method:
                            deep_calls = extract_calls(deep_method, deep_fields)
                            deep_mappers = extract_mapper_calls(deep_method)
                            deep_steps = extract_flow_steps(deep_method)
                            for m in deep_mappers:
                                if m not in all_mappers:
                                    all_mappers.append(m)
                            for dc in deep_calls:
                                dsvc = dc['service_class']
                                if dsvc:
                                    # Skip Java stdlib types
                                    if dsvc in ('Function', 'Comparator', 'Supplier', 'Consumer', 'Predicate',
                                                'Runnable', 'Callable', 'Optional', 'Stream', 'Collectors'):
                                        continue
                                    if dsvc.endswith('Dao') or dsvc.endswith('DAO'):
                                        if dsvc not in all_daos:
                                            all_daos[dsvc] = dc['object']
                                    elif dsvc not in all_services:
                                        all_services[dsvc] = dc['object']

        all_steps.extend(svc_steps)

    return {
        'services': list(all_services.keys()),
        'daos': list(all_daos.keys()),
        'mappers': all_mappers,
        'steps': all_steps,
        'calls': all_calls,
    }


def extract_class_body(content: str) -> str:
    """Extract the body of the main class."""
    # Find first class declaration
    match = re.search(
        r'(?:public\s+|private\s+|protected\s+)?(?:abstract\s+|final\s+)*'
        r'(?:class|interface)\s+\w+[^{]*\{',
        content
    )
    if not match:
        return ""
    brace_start = match.end() - 1
    end = find_brace_end(content, brace_start)
    return content[brace_start + 1:end]


# ── Markdown Generation ────────────────────────────────────────

def format_title(name: str) -> str:
    """Convert camelCase to Title Case."""
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', name).title()


def generate_endpoint_flow(
    endpoint: Dict,
    chain: Dict,
    full_url_base: str,
) -> str:
    """Generate markdown flow description for one endpoint."""
    lines = []

    http = endpoint['http_method']
    path = endpoint['path']
    name = endpoint['name']
    desc = endpoint['description']
    event_type = endpoint['event_type']

    full_url = f"{full_url_base}{path}" if path else full_url_base
    # Remove double slashes
    full_url = re.sub(r'/+', '/', full_url)

    lines.append(f"### {http} `{path or '/'}` — {format_title(name)}")
    lines.append("")

    if desc:
        lines.append(f"> {desc}")
        lines.append("")

    lines.append(f"**Full URL:** `{full_url}`")
    lines.append("")

    # Parameters
    params = endpoint['params']
    if params:
        lines.append("**Parameters:**")
        lines.append("")
        lines.append("| Name | Type | Source |")
        lines.append("|------|------|--------|")
        for p in params:
            lines.append(f"| `{p['name']}` | `{p['type']}` | {p['source']} |")
        lines.append("")

    # Event type
    if event_type:
        lines.append(f"**Event Type:** `{event_type}`")
        lines.append("")

    # Architecture: Services and Data Access
    services = chain['services']
    daos = chain['daos']
    mappers = chain['mappers']

    if services or daos or mappers:
        lines.append("**Services & Data Access:**")
        if services:
            lines.append(f"- Services: {', '.join(f'`{s}`' for s in services)}")
        if daos:
            lines.append(f"- DAOs: {', '.join(f'`{d}`' for d in daos)}")
        if mappers:
            lines.append(f"- Mappers: {', '.join(f'`{m}`' for m in mappers)}")
        lines.append("")

    # Call chain (controller → service → deeper)
    calls = chain['calls']
    if calls:
        lines.append("**Call Chain:**")
        lines.append("```")
        for obj, method in calls[:10]:
            lines.append(f"  → {obj}.{method}()")
        if len(calls) > 10:
            lines.append(f"  ... ({len(calls) - 10} more)")
        lines.append("```")
        lines.append("")

    # Business flow steps
    steps = chain['steps']
    if steps:
        lines.append("**Business Flow:**")
        lines.append("```")
        for i, step in enumerate(steps[:20], 1):
            lines.append(f"  {i}. {step}")
        if len(steps) > 20:
            lines.append(f"  ... ({len(steps) - 20} more steps)")
        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("")
    return '\n'.join(lines)


# ── Wiki Page Processing ───────────────────────────────────────

def process_controller(controller_name: str, dry_run: bool = False) -> int:
    """Process one controller and update its endpoint wiki page."""
    wiki_path = os.path.join(ENDPOINTS_DIR, f"{controller_name}.md")
    if not os.path.exists(wiki_path):
        return 0

    with open(wiki_path, 'r', encoding='utf-8') as f:
        wiki_content = f.read()

    ctrl_source = read_java_file(controller_name)
    if not ctrl_source:
        return 0

    ctrl_fields = extract_fields(ctrl_source)
    ctrl_imports = extract_imports(ctrl_source)
    endpoints = extract_endpoint_methods(ctrl_source)

    if not endpoints:
        return 0

    # Get full URL base from routing section in wiki
    full_url_base = ""
    base_match = re.search(r'\*\*Base Path:\*\*\s*`([^`]*)`', wiki_content)
    if base_match:
        full_url_base = base_match.group(1)
    routing_match = re.search(r'Full base:\s+\*\*`([^`]*)`\*\*', wiki_content)
    if routing_match:
        full_url_base = routing_match.group(1)

    # Generate flows
    flows = []
    for ep in endpoints:
        chain = trace_endpoint(ctrl_source, ctrl_fields, ctrl_imports, ep)
        flow_md = generate_endpoint_flow(ep, chain, full_url_base)
        flows.append(flow_md)

    if not flows:
        return 0

    # Build section
    flow_section = "## API Flows\n\n" + '\n'.join(flows)

    # Remove existing API Flows section if present
    if '## API Flows' in wiki_content:
        # Remove everything from ## API Flows to ## Routing Configuration or end
        pattern = r'\n## API Flows\n.*?(?=\n## Routing Configuration|\Z)'
        wiki_content = re.sub(pattern, '', wiki_content, flags=re.DOTALL).rstrip()

    # Insert before Routing Configuration
    routing_marker = "## Routing Configuration"
    if routing_marker in wiki_content:
        wiki_content = wiki_content.replace(routing_marker, flow_section + routing_marker)
    else:
        wiki_content = wiki_content.rstrip() + "\n\n" + flow_section

    if not dry_run:
        with open(wiki_path, 'w', encoding='utf-8') as f:
            f.write(wiki_content)

    return len(flows)


def main():
    parser = argparse.ArgumentParser(description='Enrich endpoint pages with API flow descriptions')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed')
    parser.add_argument('--controller', type=str, help='Process only this controller')
    parser.add_argument('--endpoints-dir', type=str, default=ENDPOINTS_DIR)
    args = parser.parse_args()

    endpoints_dir = args.endpoints_dir

    if args.controller:
        controllers = [args.controller]
    else:
        controllers = []
        for f in sorted(os.listdir(endpoints_dir)):
            if f.endswith('.md') and f != '_routing.md':
                controllers.append(f[:-3])

    print(f"Processing {len(controllers)} controllers...")
    total_flows = 0
    updated = 0

    for i, ctrl in enumerate(controllers, 1):
        count = process_controller(ctrl, dry_run=args.dry_run)
        if count > 0:
            total_flows += count
            updated += 1
            status = f"✅ {count} flows" if not args.dry_run else f"[DRY] {count} flows"
        else:
            status = "⏭️  skip"
        if i % 20 == 0 or count > 0 or args.controller:
            print(f"  [{i}/{len(controllers)}] {ctrl}: {status}")

    print(f"\n{'Would update' if args.dry_run else 'Updated'} {updated} controllers, {total_flows} endpoint flows")


if __name__ == '__main__':
    main()
