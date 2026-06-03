#!/usr/bin/env python3
"""
Enrich endpoint wiki pages with full application paths from beans.xml routing.

Reads beans.xml to build:
  bean_name → [(jaxrs_server_id, jaxrs_address)]
  
Then for each endpoint page in _endpoints/:
  - Looks up the controller class → bean_name mapping
  - Adds the full application path: /services/<jaxrs_address>/<class @Path>/<method_path>
  - Adds routing context (server, proxy config, providers)
  
Also generates a master routing reference page: _endpoints/_routing.md

Usage:
  python3 scripts/enrich_endpoints_with_routes.py          # update all
  python3 scripts/enrich_endpoints_with_routes.py --force   # force re-generate all
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = PROJECT_ROOT / "rag"
ENDPOINTS_DIR = WIKI_DIR / "mbp" / "_endpoints"
BEANS_XML = PROJECT_ROOT / "sources" / "mbp" / "web" / "WEB-INF" / "beans.xml"
if not BEANS_XML.exists():
    BEANS_XML = Path("/home/r.dovgan/mbp-rag/mbp/web/WEB-INF/beans.xml")

SERVLET_PREFIX = "/services"

NS = {
    'beans': 'http://www.springframework.org/schema/beans',
    'jaxrs': 'http://cxf.apache.org/jaxrs',
    'jaxws': 'http://cxf.apache.org/jaxws',
}


def parse_beans_xml(beans_path: str) -> dict:
    tree = ET.parse(beans_path)
    root = tree.getroot()
    
    bean_class_map = {}
    for bean in root.findall('beans:bean', NS):
        bean_id = bean.get('id') or bean.get('name')
        bean_class = bean.get('class', '')
        if bean_id and bean_class:
            bean_class_map[bean_id] = bean_class

    servers = []
    for jaxrs_server in root.findall('jaxrs:server', NS):
        server_id = jaxrs_server.get('id', '')
        address = jaxrs_server.get('address', '')
        
        service_beans = []
        for ref in jaxrs_server.findall('.//jaxrs:serviceBeans/beans:ref', NS):
            bean_ref = ref.get('bean', '')
            if bean_ref:
                service_beans.append(bean_ref)
        
        # Resolve SpringResourceFactory → beanId
        for ref in jaxrs_server.findall('.//jaxrs:serviceFactories/beans:ref', NS):
            factory_ref = ref.get('bean', '')
            if factory_ref:
                for fb in root.findall(f".//beans:bean[@id='{factory_ref}']", NS):
                    for prop in fb.findall('beans:property', NS):
                        if prop.get('name') == 'beanId':
                            factory_bean_id = prop.get('value', '')
                            if factory_bean_id:
                                service_beans.append(factory_bean_id)
        
        providers = []
        for ref in jaxrs_server.findall('.//jaxrs:providers/beans:ref', NS):
            bean_ref = ref.get('bean', '')
            if bean_ref:
                providers.append(bean_ref)
        
        out_interceptors = []
        for ref in jaxrs_server.findall('.//jaxrs:outInterceptors/beans:ref', NS):
            bean_ref = ref.get('bean', '')
            if bean_ref:
                out_interceptors.append(bean_ref)
        
        servers.append({
            'id': server_id,
            'address': address,
            'full_prefix': f"{SERVLET_PREFIX}{address}",
            'service_beans': service_beans,
            'providers': providers,
            'out_interceptors': out_interceptors,
        })
    
    soap_servers = []
    for jaxws_server in root.findall('jaxws:server', NS):
        server_id = jaxws_server.get('id', '')
        address = jaxws_server.get('address', '')
        soap_servers.append({
            'id': server_id,
            'address': address,
            'full_prefix': f"{SERVLET_PREFIX}{address}",
        })

    proxy_configs = []
    for proxy_creator in root.findall(
        "beans:bean[@class='org.springframework.aop.framework.autoproxy.BeanNameAutoProxyCreator']", NS
    ):
        proxy_name = proxy_creator.get('id') or proxy_creator.get('name', '')
        proxy_beans = []
        interceptors = []
        for prop in proxy_creator.findall('beans:property', NS):
            if prop.get('name') == 'beanNames':
                for val in prop.findall('.//beans:value', NS):
                    proxy_beans.append(val.text.strip())
            elif prop.get('name') == 'interceptorNames':
                for val in prop.findall('.//beans:value', NS):
                    interceptors.append(val.text.strip())
        proxy_configs.append({
            'name': proxy_name,
            'proxied_beans': proxy_beans,
            'interceptors': interceptors,
        })
    
    return {
        'bean_class_map': bean_class_map,
        'servers': servers,
        'soap_servers': soap_servers,
        'proxy_configs': proxy_configs,
    }


def build_class_to_routes(routing: dict) -> dict:
    bean_class_map = routing['bean_class_map']
    proxy_configs = routing['proxy_configs']
    
    bean_proxy_map = {}
    for proxy in proxy_configs:
        for bean_name in proxy['proxied_beans']:
            bean_name = bean_name.strip().strip('"')
            if bean_name not in bean_proxy_map:
                bean_proxy_map[bean_name] = []
            bean_proxy_map[bean_name].extend(proxy['interceptors'])
    
    class_routes = defaultdict(list)
    
    for server in routing['servers']:
        for bean_id in server['service_beans']:
            fqcn = bean_class_map.get(bean_id, '')
            simple_name = fqcn.rsplit('.', 1)[-1] if fqcn else bean_id
            proxy_interceptors = bean_proxy_map.get(bean_id, [])
            
            class_routes[simple_name].append({
                'server_id': server['id'],
                'server_address': server['address'],
                'full_prefix': server['full_prefix'],
                'bean_id': bean_id,
                'fqcn': fqcn,
                'providers': server.get('providers', []),
                'interceptors': proxy_interceptors,
            })
    
    for server in routing['soap_servers']:
        for bean_id in server.get('service_beans', []):
            fqcn = bean_class_map.get(bean_id, '')
            simple_name = fqcn.rsplit('.', 1)[-1] if fqcn else bean_id
            class_routes[simple_name].append({
                'server_id': server['id'],
                'server_address': server['address'],
                'full_prefix': server['full_prefix'],
                'bean_id': bean_id,
                'fqcn': fqcn,
                'protocol': 'SOAP',
            })
    
    return dict(class_routes)


def extract_base_path(content: str) -> str:
    """Extract base_path from frontmatter."""
    m = re.search(r'^base_path:\s*(.+)$', content, re.MULTILINE)
    return m.group(1).strip() if m else ''


def extract_endpoints_table(content: str) -> list:
    """Extract (method, path) pairs from the endpoints summary table."""
    results = []
    for m in re.finditer(
        r'^\|\s*\d+\s*\|\s*(\w+)\s*\|\s*`?(/[^`|\s]*)`?\s*\|',
        content, re.MULTILINE
    ):
        results.append((m.group(1), m.group(2)))
    return results


def compute_full_url(server_prefix: str, base_path: str, ep_path: str) -> str:
    """Compute full URL, handling inconsistent endpoint path formats.
    
    Some endpoint paths already include the class @Path prefix, some don't.
    E.g. base_path=/account, ep_path=/account/activity (already includes base)
    vs   base_path=/supplierapi/reservation, ep_path=/search (method-only)
    """
    base_clean = base_path.rstrip('/')
    ep_clean = ep_path.rstrip('/')
    
    if base_clean and ep_clean.startswith(base_clean):
        # Path already includes class @Path → use as-is after server prefix
        return f"{server_prefix}{ep_clean}"
    else:
        # Method-only path → prepend class @Path
        return f"{server_prefix}{base_clean}{ep_clean}"


def build_routing_section(content: str, routes: list) -> str:
    """Build the complete routing section for an endpoint page."""
    base_path = extract_base_path(content)
    endpoint_paths = extract_endpoints_table(content)
    
    lines = [""]
    lines.append("## Routing Configuration")
    lines.append("")
    
    if len(routes) == 1:
        r = routes[0]
        lines.append(f"**Servlet Prefix:** `{SERVLET_PREFIX}` (CXFServlet → `/services/*`)")
        lines.append(f"**JAX-RS Server:** `{r['server_id']}` at address `{r['server_address']}`")
        lines.append(f"**Spring Bean:** `{r['bean_id']}`")
        if r.get('fqcn'):
            lines.append(f"**Full Class:** `{r['fqcn']}`")
        if base_path:
            lines.append(f"**Class @Path:** `{base_path}`")
        lines.append("")
        lines.append("### Full Application Paths")
        lines.append("")
        full_base = f"{r['full_prefix']}{base_path.rstrip('/')}"
        lines.append(f"Full base path: **`{full_base}`**")
        lines.append("")
        lines.append("```")
        lines.append(f"{full_base}/<endpoint_path>")
        lines.append("```")
        lines.append("")
        
        if endpoint_paths:
            lines.append("")
            lines.append("| Method | Path | Full URL |")
            lines.append("|--------|------|----------|")
            for method, path in endpoint_paths:
                full_url = compute_full_url(r['full_prefix'], base_path, path)
                lines.append(f"| {method} | `{path}` | `{full_url}` |")
            lines.append("")
        
        if r.get('providers'):
            lines.append("### Server Providers")
            lines.append("")
            for p in r['providers']:
                lines.append(f"- `{p}`")
            lines.append("")
        
        if r.get('interceptors'):
            lines.append("### Proxy Interceptors")
            lines.append("")
            lines.append("This controller is wrapped by a Spring AOP proxy that applies:")
            for i in r['interceptors']:
                lines.append(f"- `{i}`")
            lines.append("")
    else:
        lines.append(f"**Servlet Prefix:** `{SERVLET_PREFIX}` (CXFServlet → `/services/*`)")
        lines.append(f"**Spring Bean:** `{routes[0]['bean_id']}`")
        if routes[0].get('fqcn'):
            lines.append(f"**Full Class:** `{routes[0]['fqcn']}`")
        if base_path:
            lines.append(f"**Class @Path:** `{base_path}`")
        lines.append("")
        lines.append("This controller is registered on **multiple JAX-RS servers**:")
        lines.append("")
        
        for r in routes:
            full_base = f"{r['full_prefix']}{base_path.rstrip('/')}"
            lines.append(f"#### Server: `{r['server_id']}` → `{r['server_address']}`")
            lines.append("")
            lines.append(f"Full base: **`{full_base}`**")
            lines.append("")
            
            if endpoint_paths:
                lines.append("| Method | Path | Full URL |")
                lines.append("|--------|------|----------|")
                for method, path in endpoint_paths:
                    full_url = compute_full_url(r['full_prefix'], base_path, path)
                    lines.append(f"| {method} | `{path}` | `{full_url}` |")
                lines.append("")
            
            if r.get('interceptors'):
                lines.append(f"Interceptors: {', '.join(f'`{i}`' for i in r['interceptors'])}")
                lines.append("")
    
    return '\n'.join(lines)


def update_endpoint_page(filepath: Path, class_routes: dict) -> bool:
    """Update a single endpoint page with routing info."""
    content = filepath.read_text(encoding='utf-8')
    
    m = re.search(r'^controller:\s*(.+)$', content, re.MULTILINE)
    if not m:
        return False
    controller_name = m.group(1).strip()
    
    routes = class_routes.get(controller_name)
    if not routes:
        return False
    
    # Strip any existing routing section (handles duplicates too)
    # Remove everything from "## Routing Configuration" to end of file
    content_clean = re.sub(
        r'\n## Routing Configuration\n.*',
        '',
        content,
        flags=re.DOTALL
    )
    
    # Remove old frontmatter flag if present
    content_clean = content_clean.replace('routing_config: true\n', '')
    
    # Add frontmatter flag
    content_clean = content_clean.replace(
        'status: generated\n',
        'status: generated\nrouting_config: true\n',
        1
    )
    
    # Build and append new routing section
    routing_section = build_routing_section(content_clean, routes)
    content_new = content_clean.rstrip() + routing_section
    
    filepath.write_text(content_new, encoding='utf-8')
    return True


def generate_routing_reference(routing: dict, class_routes: dict, output_path: Path):
    lines = []
    lines.append("---")
    lines.append("type: routing_reference")
    lines.append("title: API Routing Configuration")
    lines.append(f"generated_at: {datetime.now().isoformat()}")
    lines.append("---")
    lines.append("")
    lines.append("# API Routing Configuration")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append("The MBP application uses Apache CXF with Spring XML configuration for REST/SOAP routing.")
    lines.append("")
    lines.append("### Request Flow")
    lines.append("")
    lines.append("```")
    lines.append("Client Request")
    lines.append("    │")
    lines.append("    ▼")
    lines.append("ShiroFilter (/*) — Authentication/Authorization")
    lines.append("    │")
    lines.append("    ▼")
    lines.append("CXFServlet (/services/*) — from web.xml")
    lines.append("    │")
    lines.append("    ▼")
    lines.append("JAX-RS Server (address=/rest, /json, /json/v2, etc.) — from beans.xml")
    lines.append("    │")
    lines.append("    ▼")
    lines.append("Spring AOP Proxy (BeanNameAutoProxyCreator) — Exception handling")
    lines.append("    │")
    lines.append("    ▼")
    lines.append("Controller Class (@Path annotation)")
    lines.append("    │")
    lines.append("    ▼")
    lines.append("Method (@GET/@POST/@PUT/@DELETE + @Path)")
    lines.append("```")
    lines.append("")
    lines.append(f"**Full URL pattern:** `{SERVLET_PREFIX}/<jaxrs_address>/<class_@Path>/<method_@Path>`")
    lines.append("")
    
    lines.append("## Servlet Mappings (web.xml)")
    lines.append("")
    lines.append("| Servlet | URL Pattern | Config |")
    lines.append("|---------|------------|--------|")
    lines.append(f"| CXFServlet (`XMLServer`) | `/services/*` | `/WEB-INF/beans.xml` |")
    lines.append(f"| RazorServer | `/razor/RazorService` | GWT RPC |")
    lines.append(f"| JSONServer | `/JSONServer/*` | JSON-RPC |")
    lines.append(f"| JSONService | `/JSONService/*` | Widget JSON |")
    lines.append(f"| FileUploadServer | `/razor/UploadFileService` | File upload |")
    lines.append("")
    
    lines.append("## JAX-RS Servers (beans.xml)")
    lines.append("")
    lines.append("| Server ID | Address | Full Prefix | Controllers | Providers |")
    lines.append("|-----------|---------|-------------|-------------|-----------|")
    
    for server in routing['servers']:
        n_beans = len(server['service_beans'])
        providers_str = ', '.join(server.get('providers', [])) or '—'
        if len(providers_str) > 60:
            providers_str = providers_str[:57] + "..."
        lines.append(f"| `{server['id']}` | `{server['address']}` | `{server['full_prefix']}` | {n_beans} | {providers_str} |")
    lines.append("")
    
    if routing['soap_servers']:
        lines.append("## SOAP Servers (beans.xml)")
        lines.append("")
        for server in routing['soap_servers']:
            lines.append(f"- **`{server['id']}`** at `{server['full_prefix']}`")
        lines.append("")
    
    lines.append("## Server Details — Controller Registration")
    lines.append("")
    
    for server in routing['servers']:
        lines.append(f"### `{server['id']}` — `{server['full_prefix']}`")
        lines.append("")
        if server.get('providers'):
            lines.append(f"**Providers:** {', '.join(f'`{p}`' for p in server['providers'])}")
            lines.append("")
        if server.get('out_interceptors'):
            lines.append(f"**Out Interceptors:** {', '.join(f'`{p}`' for p in server['out_interceptors'])}")
            lines.append("")
        lines.append("| Bean ID | Controller Class |")
        lines.append("|---------|-----------------|")
        for bean_id in server['service_beans']:
            fqcn = routing['bean_class_map'].get(bean_id, '?')
            simple = fqcn.rsplit('.', 1)[-1] if '.' in fqcn else fqcn
            lines.append(f"| `{bean_id}` | [{simple}](./{simple}.md) |")
        lines.append("")
    
    if routing['proxy_configs']:
        lines.append("## AOP Proxy Configuration")
        lines.append("")
        lines.append("Spring AOP proxies wrap controller beans for cross-cutting concerns:")
        lines.append("")
        for proxy in routing['proxy_configs']:
            lines.append(f"### `{proxy['name']}`")
            lines.append("")
            lines.append(f"**Interceptors:** {', '.join(f'`{i}`' for i in proxy['interceptors'])}")
            lines.append("")
            lines.append(f"**Proxied beans ({len(proxy['proxied_beans'])}):**")
            lines.append("")
            for bean_name in sorted(set(proxy['proxied_beans'])):
                bean_name = bean_name.strip().strip('"')
                fqcn = routing['bean_class_map'].get(bean_name, '')
                simple = fqcn.rsplit('.', 1)[-1] if '.' in fqcn else bean_name
                lines.append(f"- `{bean_name}` → {simple}")
            lines.append("")
    
    # Quick reference
    lines.append("## Controller → Full Paths Quick Reference")
    lines.append("")
    lines.append("| Controller | @Path | Servers | Full Base Paths |")
    lines.append("|-----------|-------|---------|----------------|")
    
    endpoint_base_paths = {}
    if ENDPOINTS_DIR.is_dir():
        for ep_file in ENDPOINTS_DIR.glob("*.md"):
            if ep_file.name.startswith('_'):
                continue
            m = re.search(r'^base_path:\s*(.+)$', ep_file.read_text(encoding='utf-8'), re.MULTILINE)
            if m:
                endpoint_base_paths[ep_file.stem] = m.group(1).strip()
    
    for ctrl_name in sorted(class_routes.keys()):
        routes = class_routes[ctrl_name]
        base_path = endpoint_base_paths.get(ctrl_name, '?')
        server_ids = ', '.join(f'`{r["server_id"]}`' for r in routes)
        full_paths = ', '.join(f'`{r["full_prefix"]}{base_path.rstrip("/")}`' for r in routes)
        lines.append(f"| [{ctrl_name}](./{ctrl_name}.md) | `{base_path}` | {server_ids} | {full_paths} |")
    lines.append("")
    
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Generated routing reference: {output_path}")


def main():
    print(f"Parsing beans.xml: {BEANS_XML}")
    if not BEANS_XML.exists():
        print(f"ERROR: beans.xml not found at {BEANS_XML}")
        sys.exit(1)
    
    routing = parse_beans_xml(str(BEANS_XML))
    
    print(f"  Found {len(routing['servers'])} JAX-RS servers")
    print(f"  Found {len(routing['soap_servers'])} SOAP servers")
    print(f"  Found {len(routing['bean_class_map'])} bean definitions")
    print(f"  Found {len(routing['proxy_configs'])} proxy configurations")
    
    class_routes = build_class_to_routes(routing)
    print(f"  Mapped {len(class_routes)} controller classes to routes")
    
    generate_routing_reference(routing, class_routes, ENDPOINTS_DIR / "_routing.md")
    
    if not ENDPOINTS_DIR.is_dir():
        print(f"ERROR: Endpoints dir not found: {ENDPOINTS_DIR}")
        sys.exit(1)
    
    updated = 0
    no_route = 0
    
    for ep_file in sorted(ENDPOINTS_DIR.glob("*.md")):
        if ep_file.name.startswith('_'):
            continue
        
        content = ep_file.read_text(encoding='utf-8')
        m = re.search(r'^controller:\s*(.+)$', content, re.MULTILINE)
        if not m:
            continue
        
        controller_name = m.group(1).strip()
        if controller_name not in class_routes:
            no_route += 1
            print(f"  No route for: {controller_name}")
            continue
        
        if update_endpoint_page(ep_file, class_routes):
            updated += 1
    
    print(f"\nEndpoint pages updated: {updated}")
    print(f"No route found: {no_route}")
    print(f"\nDone. Reindex to apply: python3 run_rag.py index")


if __name__ == '__main__':
    main()
