#!/usr/bin/env python3
"""
Entity → Database Table Mapping Generator.

Reads the already-parsed data from parsed.json and builds a comprehensive
mapping from business entities (Java classes) to their MySQL tables via
MyBatis mapper XML analysis.

Generates:
  1. rag/entity-table-map.md    — human-readable mapping document (indexed by RAG)
  2. data/entity_table_map.json — machine-readable mapping (for programmatic use)

Usage:
  python3 generate_entity_table_map.py
  python3 generate_entity_table_map.py --module dataaccesslayer   # one module only
"""

import os
import re
import json
import argparse
import logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
PARSED_FILE = DATA_DIR / "parsed" / "parsed.json"
WIKI_DIR = PROJECT_ROOT / "rag"
OUTPUT_MAP = DATA_DIR / "entity_table_map.json"
OUTPUT_MD = WIKI_DIR / "entity-table-map.md"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# SQL keywords to ignore when extracting table names
SQL_KEYWORDS = {
    'select', 'set', 'where', 'and', 'or', 'not', 'null', 'in', 'as',
    'on', 'from', 'into', 'values', 'group', 'order', 'by', 'having',
    'limit', 'offset', 'join', 'left', 'right', 'inner', 'outer',
    'create', 'drop', 'alter', 'index', 'table', 'insert', 'update',
    'delete', 'with', 'case', 'when', 'then', 'else', 'end', 'exists',
    'between', 'like', 'is', 'distinct', 'all', 'any', 'some', 'union',
    'intersect', 'except', 'true', 'false', 'asc', 'desc', 'primary',
    'key', 'foreign', 'references', 'constraint', 'default', 'check',
    'unique', 'auto_increment', 'if', 'using', 'natural', 'cross',
    'information_schema', 'columns', 'tables', 'schema',
}


def extract_tables_from_sql(sql: str) -> list:
    """Extract table names from a SQL statement."""
    tables = []
    # Remove comments
    sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    
    # Also handle <include> refs (MyBatis SQL fragments) — just skip them
    
    patterns = [
        r'(?i)\bFROM\s+`?([a-zA-Z_][\w_]*)`?',
        r'(?i)\bINTO\s+`?([a-zA-Z_][\w_]*)`?',
        r'(?i)\bUPDATE\s+`?([a-zA-Z_][\w_]*)`?',
        r'(?i)\bJOIN\s+`?([a-zA-Z_][\w_]*)`?',
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, sql):
            name = m.group(1).lower()
            if name not in SQL_KEYWORDS and len(name) > 2:
                tables.append(name)
    return tables


def build_mapper_table_map(parsed_data: dict) -> dict:
    """
    Build: mapper_namespace -> {primary_table, all_tables, statements}
    """
    result = {}
    for mod in parsed_data.get('modules', []):
        for mapper in mod.get('mappers', []):
            ns = mapper.get('namespace', '')
            if not ns or ns.startswith('$'):
                continue

            all_tables = set()
            primary_table = None
            write_tables = set()  # tables this mapper writes to
            
            for stmt in mapper.get('statements', []):
                sql = stmt.get('sql_preview', '')
                if not sql:
                    continue
                tables = extract_tables_from_sql(sql)
                all_tables.update(tables)
                
                stmt_type = stmt.get('type', '')
                if stmt_type == 'insert':
                    for t in tables:
                        write_tables.add(t)
                        if primary_table is None:
                            primary_table = t
                elif stmt_type == 'update':
                    for t in tables:
                        write_tables.add(t)
                        if primary_table is None:
                            primary_table = t
                elif stmt_type == 'delete':
                    for t in tables:
                        write_tables.add(t)

            # Fallback: primary = first table from any statement
            if primary_table is None and all_tables:
                primary_table = sorted(all_tables)[0]

            result[ns] = {
                'primary_table': primary_table,
                'all_tables': sorted(all_tables),
                'write_tables': sorted(write_tables),
                'statement_count': len(mapper.get('statements', [])),
                'module': mod.get('module', ''),
            }
    return result


def build_short_name_map(mapper_table_map: dict) -> dict:
    """Mapper short name -> full namespace."""
    result = {}
    for ns in mapper_table_map:
        short = ns.rsplit('.', 1)[-1] if '.' in ns else ns
        result[short] = ns
    return result


def build_dao_mapper_chain(parsed_data: dict) -> dict:
    """
    Build: DAO class name -> {mapper_short_name, dao_package, module}
    """
    result = {}
    for mod in parsed_data.get('modules', []):
        for cls in mod.get('classes', []):
            stereotype = cls.get('spring_stereotype', '')
            name = cls.get('name', '')
            if stereotype == '@Repository' and ('Dao' in name or 'DAO' in name):
                mapper_fields = []
                for f in cls.get('fields', []):
                    tn = f.get('type_name', '').strip()
                    if 'Mapper' in tn:
                        mapper_fields.append(tn)
                if mapper_fields:
                    result[name] = {
                        'mapper_short_names': mapper_fields,
                        'dao_package': cls.get('package', ''),
                        'module': cls.get('module', ''),
                    }
    return result


def build_entity_interface_map(parsed_data: dict) -> dict:
    """
    Build: class name -> {implements: [Is* interfaces], module, package}
    Also includes model/entity/DTO classes that are likely table-backed,
    even if they don't implement Is* interfaces.
    """
    result = {}
    for mod in parsed_data.get('modules', []):
        for cls in mod.get('classes', []):
            implements = cls.get('implements', [])
            is_impl = [i for i in implements
                       if i.startswith('Is') or 'Cacheable' in i
                       or 'HasState' in i or 'Cloneable' in i]
            # Also include classes from dal.shared / dal.entity / dao.dto packages
            # that look like entity/model classes (not Dao, Service, Controller, etc.)
            pkg = cls.get('package', '')
            name = cls.get('name', '')
            is_entity_package = (
                'dal.shared' in pkg or 'dal.entity' in pkg
                or 'dao.dto' in pkg or 'dto' in pkg.split('.')
            )
            skip_suffixes = ('Dao', 'DAO', 'Service', 'Controller', 'RestController',
                             'Mapper', 'Handler', 'Filter', 'Builder', 'Factory',
                             'Utils', 'Util', 'Helper', 'Config', 'Constant', 'Exception')
            is_entity_class = (
                is_entity_package
                and not any(name.endswith(s) for s in skip_suffixes)
                and cls.get('class_type') == 'class'
                and not cls.get('spring_stereotype')
            )

            if is_impl or is_entity_class:
                if cls['name'] not in result:  # don't overwrite Is* matches
                    result[cls['name']] = {
                        'implements': is_impl if is_impl else ['Model/Entity'],
                        'package': pkg,
                        'module': cls.get('module', ''),
                    }
    return result


def build_service_dao_chain(parsed_data: dict) -> dict:
    """
    Build: Service class name -> [DAO class names it depends on]
    """
    result = {}
    for mod in parsed_data.get('modules', []):
        for cls in mod.get('classes', []):
            stereotype = cls.get('spring_stereotype', '')
            if stereotype in ('@Service', '@Component') and 'Service' in cls.get('name', ''):
                dao_deps = []
                for f in cls.get('fields', []):
                    tn = f.get('type_name', '').strip()
                    if 'Dao' in tn or 'DAO' in tn:
                        dao_deps.append(tn)
                if dao_deps:
                    result[cls['name']] = {
                        'dao_deps': dao_deps,
                        'module': cls.get('module', ''),
                        'package': cls.get('package', ''),
                    }
    return result


def build_full_chain(
    mapper_table_map: dict,
    short_name_map: dict,
    dao_mapper_chain: dict,
    entity_interface_map: dict,
    service_dao_chain: dict,
) -> dict:
    """
    Build the full mapping:
      entity_table_map[primary_table] = {
        table, mapper, dao, entity_class, services, ...
      }
    """
    # Table -> full info
    table_map = defaultdict(lambda: {
        'table': '',
        'mappers': [],
        'daos': [],
        'entity_classes': [],
        'services': [],
        'read_only_tables': [],
    })

    # 1. Mapper -> Table
    for ns, info in mapper_table_map.items():
        short = ns.rsplit('.', 1)[-1] if '.' in ns else ns
        primary = info['primary_table']
        if primary:
            table_map[primary]['table'] = primary
            table_map[primary]['mappers'].append({
                'namespace': ns,
                'short_name': short,
                'module': info['module'],
                'all_tables': info['all_tables'],
            })
        # Also index secondary tables
        for t in info['all_tables']:
            if t != primary:
                table_map[t]['read_only_tables'].append(short)

    # 2. DAO -> Mapper -> Table
    for dao_name, dao_info in dao_mapper_chain.items():
        for mapper_short in dao_info['mapper_short_names']:
            ns = short_name_map.get(mapper_short)
            if ns and ns in mapper_table_map:
                primary = mapper_table_map[ns]['primary_table']
                if primary and primary in table_map:
                    table_map[primary]['daos'].append({
                        'name': dao_name,
                        'package': dao_info['dao_package'],
                        'module': dao_info['module'],
                        'mapper': mapper_short,
                    })

    # 3. Entity classes -> Table (by naming convention)
    #    e.g., Fee -> fee, ReservationModel -> reservation, Product -> product
    for cls_name, cls_info in entity_interface_map.items():
        # Try to match entity class name to a table
        # Derive candidates with various naming strategies
        snake = re.sub(r'([A-Z])', r'_\\1', cls_name).lower().lstrip('_')
        candidates = [
            cls_name.lower(),                                          # Fee -> fee
            snake,                                                    # FeeTaxRelation -> fee_tax_relation
            cls_name.lower().replace('model', ''),                     # ReservationModel -> reservation
            snake.replace('_model', ''),                               # reservation_model -> reservation
            cls_name.lower() + 's',                                    # Tax -> taxes (plural)
            snake + 's',                                              # fee_tax_relation -> fee_tax_relations
            cls_name.lower() + '_active',                              # Price -> price_active
            snake + '_active',                                        # los_price -> los_price_active
        ]
        for candidate in candidates:
            if candidate in table_map:
                table_map[candidate]['entity_classes'].append({
                    'name': cls_name,
                    'package': cls_info['package'],
                    'module': cls_info['module'],
                    'interfaces': cls_info['implements'],
                })
                break

    # 4. Service -> DAO -> Table
    dao_names = set(dao_mapper_chain.keys())
    for svc_name, svc_info in service_dao_chain.items():
        for dao_dep in svc_info['dao_deps']:
            # dao_dep is a type name like "ReservationDao"
            if dao_dep in dao_names:
                for mapper_short in dao_mapper_chain[dao_dep]['mapper_short_names']:
                    ns = short_name_map.get(mapper_short)
                    if ns and ns in mapper_table_map:
                        primary = mapper_table_map[ns]['primary_table']
                        if primary and primary in table_map:
                            table_map[primary]['services'].append({
                                'name': svc_name,
                                'module': svc_info['module'],
                                'package': svc_info['package'],
                            })

    return dict(table_map)


def generate_markdown(table_map: dict, output_path: Path):
    """Generate the entity-table-map.md document."""
    lines = [
        "---",
        "title: Entity → Database Table Mapping",
        "generated_at: " + datetime.now().isoformat(),
        "tables: " + str(len(table_map)),
        "status: approved",
        "---",
        "",
        "# Entity → Database Table Mapping",
        "",
        "This document maps **business entities** (Java classes) to their **MySQL database tables** "
        "through the MyBatis persistence layer. Use this to understand which table backs a given entity.",
        "",
        "## Legend",
        "",
        "| Symbol | Meaning |",
        "|--------|---------|",
        "| **Entity** | Java model/DTO class implementing `Is*` interfaces |",
        "| **DAO** | `@Repository` class wrapping a MyBatis mapper |",
        "| **Mapper** | MyBatis XML mapper (SQL statements) |",
        "| **Service** | `@Service` class using the DAO |",
        "| **Table** | MySQL table name |",
        "",
        "## Mapping",
        "",
    ]

    # Sort by table name
    for table_name in sorted(table_map.keys()):
        info = table_map[table_name]
        if not info['mappers']:
            continue

        primary_mapper = info['mappers'][0]
        all_tables = set()
        for m in info['mappers']:
            all_tables.update(m.get('all_tables', []))
        all_tables.discard(table_name)

        lines.append(f"### `{table_name}`")
        lines.append("")

        # Mapper info
        mapper_names = [f"`{m['short_name']}`" for m in info['mappers']]
        lines.append(f"- **Mappers:** {', '.join(mapper_names)}")
        lines.append(f"- **Module:** `{primary_mapper['module']}`")

        # DAO info
        if info['daos']:
            dao_names = [f"`{d['name']}`" for d in info['daos']]
            lines.append(f"- **DAOs:** {', '.join(dao_names)}")
        else:
            lines.append(f"- **DAOs:** *(not linked via @Repository)*")

        # Entity classes
        if info['entity_classes']:
            entity_strs = []
            for e in info['entity_classes']:
                ifaces = ', '.join(e['interfaces'][:3])
                entity_strs.append(f"`{e['name']}` ({ifaces})")
            lines.append(f"- **Entity classes:** {', '.join(entity_strs)}")
        else:
            lines.append(f"- **Entity classes:** *(no Is* interface match)*")

        # Services
        if info['services']:
            svc_names = sorted(set(f"`{s['name']}`" for s in info['services']))
            if len(svc_names) <= 8:
                lines.append(f"- **Used by services:** {', '.join(svc_names)}")
            else:
                lines.append(f"- **Used by services:** {', '.join(svc_names[:8])} and {len(svc_names)-8} more")

        # Related tables
        if all_tables:
            lines.append(f"- **Related tables:** {', '.join(f'`{t}`' for t in sorted(all_tables)[:10])}")

        lines.append("")

    # Also generate reverse index: Entity class -> table
    lines.append("---")
    lines.append("")
    lines.append("## Reverse Index: Entity Class → Table")
    lines.append("")
    lines.append("| Entity Class | Interfaces | Primary Table | DAO |")
    lines.append("|-------------|-----------|---------------|-----|")

    entity_to_table = []
    for table_name, info in sorted(table_map.items()):
        for e in info.get('entity_classes', []):
            entity_to_table.append((e['name'], ', '.join(e['interfaces'][:3]), table_name,
                                     ', '.join(d['name'] for d in info['daos'][:2])))
    
    # Also add DAOs without entity matches
    for table_name, info in sorted(table_map.items()):
        if info['daos'] and not info['entity_classes']:
            for d in info['daos']:
                entity_to_table.append((d['name'], '@Repository', table_name, d['name']))

    for name, ifaces, table, dao in sorted(entity_to_table):
        lines.append(f"| `{name}` | {ifaces} | `{table}` | `{dao}` |")

    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(lines), encoding='utf-8')
    log.info(f"Generated {output_path} ({len(table_map)} tables)")


def generate_json(table_map: dict, output_path: Path):
    """Generate machine-readable JSON mapping."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(table_map, indent=2, ensure_ascii=False), encoding='utf-8')
    log.info(f"Generated {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate entity→table mapping")
    parser.add_argument("--module", help="Filter to a single module")
    args = parser.parse_args()

    if not PARSED_FILE.exists():
        log.error(f"Missing {PARSED_FILE}. Run `python3 run_rag.py parse` first.")
        return

    with open(PARSED_FILE) as f:
        parsed_data = json.load(f)

    log.info(f"Loaded parsed data: {len(parsed_data.get('modules', []))} modules")

    # Build all the maps
    mapper_table_map = build_mapper_table_map(parsed_data)
    log.info(f"Found {len(mapper_table_map)} mapper namespaces with table references")

    short_name_map = build_short_name_map(mapper_table_map)
    dao_mapper_chain = build_dao_mapper_chain(parsed_data)
    log.info(f"Found {len(dao_mapper_chain)} DAOs with mapper dependencies")

    entity_interface_map = build_entity_interface_map(parsed_data)
    log.info(f"Found {len(entity_interface_map)} entity classes implementing Is* interfaces")

    service_dao_chain = build_service_dao_chain(parsed_data)
    log.info(f"Found {len(service_dao_chain)} services with DAO dependencies")

    # Build the full chain
    table_map = build_full_chain(
        mapper_table_map, short_name_map, dao_mapper_chain,
        entity_interface_map, service_dao_chain
    )
    log.info(f"Built mapping for {len(table_map)} tables")

    # Generate outputs
    generate_json(table_map, OUTPUT_MAP)
    generate_markdown(table_map, OUTPUT_MD)

    # Print summary
    tables_with_dao = sum(1 for v in table_map.values() if v['daos'])
    tables_with_entity = sum(1 for v in table_map.values() if v['entity_classes'])
    tables_with_service = sum(1 for v in table_map.values() if v['services'])
    
    print(f"\n{'='*60}")
    print(f"Entity → Table Mapping Summary")
    print(f"{'='*60}")
    print(f"Total tables mapped:     {len(table_map)}")
    print(f"Tables with DAO:         {tables_with_dao}")
    print(f"Tables with entity class: {tables_with_entity}")
    print(f"Tables with service:     {tables_with_service}")
    print(f"\nOutputs:")
    print(f"  Markdown: {OUTPUT_MD}")
    print(f"  JSON:     {OUTPUT_MAP}")
    print(f"\nNext steps:")
    print(f"  1. Review: cat {OUTPUT_MD} | head -100")
    print(f"  2. Re-index: python3 run_rag.py index")
    print(f"  3. Query: python3 run_rag.py query 'which table stores reservations?'")


if __name__ == '__main__':
    main()
