"""
ChromaDB indexer — indexes Markdown wiki files for RAG queries.

Supports resume: re-running continues from where it stopped.
"""

import os
import re
import logging
import yaml
from typing import List, Dict, Optional
from datetime import datetime

log = logging.getLogger(__name__)


def chunk_markdown(content: str, file_path: str, max_chunk_size: int = 2000) -> List[Dict]:
    """Split Markdown content into chunks by headers.
    
    For endpoint pages (_endpoints/), uses larger chunks to keep
    the endpoint table and routing info together.
    """
    # Use larger chunks for endpoint pages to keep routing tables intact
    if '/_endpoints/' in file_path:
        max_chunk_size = 4000
    metadata = {}
    body = content
    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            fm = content[3:end].strip()
            try:
                metadata = yaml.safe_load(fm) or {}
                metadata = {k: str(v) for k, v in metadata.items()}
            except yaml.YAMLError:
                # Fallback to simple line-by-line parsing
                for line in fm.split('\n'):
                    if ':' in line:
                        key, _, val = line.partition(':')
                        metadata[key.strip()] = val.strip()
            body = content[end + 3:].strip()

    sections = []
    current_header = ""
    current_lines = []

    for line in body.split('\n'):
        if line.startswith('#'):
            if current_lines:
                text = '\n'.join(current_lines).strip()
                if text:
                    sections.append({'header': current_header, 'text': text})
            current_header = line.lstrip('#').strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        text = '\n'.join(current_lines).strip()
        if text:
            sections.append({'header': current_header, 'text': text})

    if not sections:
        sections = [{'header': '', 'text': body}]

    chunks = []
    for section in sections:
        text = section['text']
        if len(text) <= max_chunk_size:
            chunks.append({'text': text, 'header': section['header'], 'metadata': {**metadata}})
        else:
            paragraphs = text.split('\n\n')
            buffer = ""
            for para in paragraphs:
                if len(buffer) + len(para) > max_chunk_size and buffer:
                    chunks.append({'text': buffer.strip(), 'header': section['header'], 'metadata': {**metadata}})
                    buffer = para
                else:
                    buffer += '\n\n' + para if buffer else para
            if buffer.strip():
                chunks.append({'text': buffer.strip(), 'header': section['header'], 'metadata': {**metadata}})

    # Filter tiny chunks
    # Inject source file title into every chunk for better context
    page_title = ''
    for section in sections:
        if section['header']:
            page_title = section['header']
            break
    
    chunks = [c for c in chunks if len(c['text'].strip()) > 50]

    for chunk in chunks:
        # Prepend page title to chunk text for context when chunk doesn't start with header
        if page_title and not chunk['text'].lstrip().startswith('#'):
            chunk['text'] = f"({page_title})\n" + chunk['text']
        chunk['metadata']['source_file'] = file_path
        chunk['metadata']['indexed_at'] = datetime.now().isoformat()

    return chunks


def _get_indexed_files(collection) -> set:
    """Extract set of source_file values already in the collection."""
    indexed = set()
    try:
        batch_size = 5000
        total = collection.count()
        offset = 0
        while offset < total:
            # Use offset-based pagination instead of sequential IDs
            result = collection.get(
                limit=batch_size,
                offset=offset,
                include=["metadatas"],
            )
            if not result.get('ids'):
                break
            for meta in result.get('metadatas', []):
                sf = meta.get('source_file', '') if meta else ''
                if sf:
                    indexed.add(sf)
            offset += batch_size
            if offset % 50000 == 0:
                log.info(f"  Scanned {offset}/{total} existing chunks...")
    except Exception as e:
        log.warning(f"Could not scan existing indexed files: {e}")
    return indexed


def build_vectorstore(
    wiki_dir: str,
    store_dir: str,
    collection_name: str = "wiki_java",
    embedding_model: str = "all-MiniLM-L6-v2",
    batch_size: int = 500,
    incremental: bool = True,
    cpu_limit: int = 1,
    only_files: list = None,
):
    """
    Index Markdown files into ChromaDB.

    Modes:
      incremental=True  — only index NEW/CHANGED files (fast, low CPU)
      incremental=False — full reindex (use --force-index flag)
      only_files=[...]  — only index specific files

    cpu_limit: cap number of threads used for embedding.
    """
    import chromadb
    from sentence_transformers import SentenceTransformer

    # ── CPU throttling ─────────────────────────────────────────
    if cpu_limit > 0:
        try:
            os.sched_setaffinity(0, list(range(min(cpu_limit, os.cpu_count() or 1))))
        except AttributeError:
            pass  # macOS lacks sched_setaffinity
        import torch
        if torch.cuda.is_available():
            pass  # GPU — let it be
        else:
            torch.set_num_threads(cpu_limit)
            log.info(f"CPU limited to {cpu_limit} thread(s)")

    log.info(f"Loading embedding model: {embedding_model}")
    encoder = SentenceTransformer(embedding_model)

    client = chromadb.PersistentClient(path=store_dir)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "Java codebase RAG knowledge base"}
    )
    existing_count = collection.count()
    log.info(f"Collection '{collection_name}': {existing_count} existing chunks")

    # ── Find Markdown files ─────────────────────────────────────
    md_files = []
    if only_files:
        for f in only_files:
            full = os.path.join(wiki_dir, f) if not os.path.isabs(f) else f
            if os.path.exists(full):
                md_files.append(full)
        log.info(f"Targeting {len(md_files)} specific files")
    else:
        for root, dirs, files in os.walk(wiki_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if f.endswith('.md'):
                    md_files.append(os.path.join(root, f))
        log.info(f"Found {len(md_files)} Markdown files")

    # ── Clean up stale chunks & find new files ──────────────
    if incremental:
        all_wiki_files = set()
        for root, dirs, files in os.walk(wiki_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if f.endswith('.md'):
                    rel = os.path.join(root, f).replace(wiki_dir, '').lstrip('/')
                    all_wiki_files.add(rel)
        
        log.info("Scanning existing index for incremental update...")
        indexed_files = _get_indexed_files(collection)
        log.info(f"Found {len(indexed_files)} unique files already indexed")
        
        # Remove chunks for files that no longer exist on disk
        stale_files = indexed_files - all_wiki_files
        if stale_files:
            log.info(f"Found {len(stale_files)} stale files to remove from index")
            stale_ids = []
            batch_size_del = 5000
            total_existing = collection.count()
            for offset in range(0, total_existing, batch_size_del):
                result = collection.get(
                    limit=batch_size_del,
                    offset=offset,
                    include=["metadatas"],
                )
                if not result.get('ids'):
                    break
                for i, meta in enumerate(result.get('metadatas', [])):
                    if meta and meta.get('source_file', '') in stale_files:
                        stale_ids.append(result['ids'][i])
            if stale_ids:
                for i in range(0, len(stale_ids), 1000):
                    collection.delete(ids=stale_ids[i:i+1000])
                log.info(f"Removed {len(stale_ids)} stale chunks from {len(stale_files)} deleted files")
        
        # Filter to only new/changed files
        new_files = []
        for fp in md_files:
            rel = fp.replace(wiki_dir, '').lstrip('/')
            if rel not in indexed_files:
                new_files.append(fp)
        log.info(f"New/changed files to index: {len(new_files)} (skipping {len(md_files) - len(new_files)} existing)")
        md_files = new_files

        if not md_files:
            log.info("✅ Nothing new to index")
            return {"collection": collection_name, "total_chunks": collection.count(), "indexed_now": 0}
    elif only_files:
        # For specific files, always index them (upsert)
        pass

    # ── Chunk files ─────────────────────────────────────────────
    all_chunks = []
    for file_path in md_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            rel_path = file_path.replace(wiki_dir, '').lstrip('/')
            file_chunks = chunk_markdown(content, rel_path)
            all_chunks.extend(file_chunks)
        except Exception as e:
            log.warning(f"Failed to read {file_path}: {e}")

    log.info(f"Total new chunks: {len(all_chunks)}")

    if not all_chunks:
        log.info("✅ No chunks to index")
        return {"collection": collection_name, "total_chunks": existing_count, "indexed_now": 0}

    # ── Batch embed and upsert ──────────────────────────────────
    total_batches = (len(all_chunks) + batch_size - 1) // batch_size
    log.info(f"Embedding {len(all_chunks)} chunks in {total_batches} batches (batch_size={batch_size})")

    # Use stable IDs based on source file + chunk index to allow upsert
    for idx, chunk in enumerate(all_chunks):
        src = chunk['metadata'].get('source_file', '').replace('/', '_').replace('.', '_')
        chunk['_id'] = f"inc_{src}_{idx}"

    done = 0
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        texts = [c['text'] for c in batch]
        metas = [c['metadata'] for c in batch]
        ids = [c['_id'] for c in batch]

        done += 1
        log.info(f"Embedding batch {done}/{total_batches} ({len(batch)} chunks)")

        embeddings = encoder.encode(texts, show_progress_bar=False).tolist()

        collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metas,
        )

    total = collection.count()
    log.info(f"✅ Indexed {len(all_chunks)} new chunks. Collection total: {total}")
    return {"collection": collection_name, "total_chunks": total, "indexed_now": len(all_chunks)}


def query_rag(
    query: str,
    store_dir: str,
    collection_name: str = "wiki_java",
    top_k: int = 5,
    embedding_model: str = "all-MiniLM-L6-v2",
    filter_metadata: Optional[Dict] = None,
) -> List[Dict]:
    """Query the RAG pipeline. Returns results with text, metadata, distance."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    encoder = SentenceTransformer(embedding_model)
    client = chromadb.PersistentClient(path=store_dir)

    try:
        collection = client.get_collection(collection_name)
    except Exception as e:
        log.error(f"Collection '{collection_name}' not found: {e}")
        return []

    query_embedding = encoder.encode([query]).tolist()

    kwargs = {
        "query_embeddings": query_embedding,
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if filter_metadata:
        kwargs["where"] = filter_metadata

    results = collection.query(**kwargs)

    formatted = []
    for i in range(len(results['ids'][0])):
        formatted.append({
            'id': results['ids'][0][i],
            'text': results['documents'][0][i],
            'metadata': results['metadatas'][0][i],
            'distance': results['distances'][0][i],
        })
    return formatted
