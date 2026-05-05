"""
ChromaDB indexer — indexes Markdown wiki files for RAG queries.

Supports resume: re-running continues from where it stopped.
"""

import os
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime

log = logging.getLogger(__name__)


def chunk_markdown(content: str, file_path: str, max_chunk_size: int = 1500) -> List[Dict]:
    """Split Markdown content into chunks by headers."""
    metadata = {}
    body = content
    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            fm = content[3:end].strip()
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
    chunks = [c for c in chunks if len(c['text'].strip()) > 50]

    for chunk in chunks:
        chunk['metadata']['source_file'] = file_path
        chunk['metadata']['indexed_at'] = datetime.now().isoformat()

    return chunks


def build_vectorstore(
    wiki_dir: str,
    store_dir: str,
    collection_name: str = "wiki_java",
    embedding_model: str = "all-MiniLM-L6-v2",
    batch_size: int = 500,
):
    """Index all Markdown files. Resumes from where it stopped."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    log.info(f"Loading embedding model: {embedding_model}")
    encoder = SentenceTransformer(embedding_model)

    client = chromadb.PersistentClient(path=store_dir)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "Java codebase RAG knowledge base"}
    )
    existing_count = collection.count()
    log.info(f"Collection '{collection_name}': {existing_count} existing chunks")

    # Find all Markdown files
    md_files = []
    for root, dirs, files in os.walk(wiki_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith('.md'):
                md_files.append(os.path.join(root, f))

    log.info(f"Found {len(md_files)} Markdown files to index")

    # Chunk all files
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

    log.info(f"Total chunks: {len(all_chunks)}")

    # Resume: skip already indexed
    start_offset = existing_count
    if start_offset >= len(all_chunks):
        log.info(f"✅ Already fully indexed ({existing_count} chunks)")
        return {"collection": collection_name, "total_chunks": existing_count, "total_files": len(md_files)}

    remaining = len(all_chunks) - start_offset
    total_batches = (remaining + batch_size - 1) // batch_size
    log.info(f"Resuming from chunk {start_offset}, {remaining} remaining ({total_batches} batches)")

    # Batch embed and upsert
    done = 0
    for i in range(start_offset, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        texts = [c['text'] for c in batch]
        metas = [c['metadata'] for c in batch]
        ids = [f"chunk_{i + j}" for j in range(len(batch))]

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
    log.info(f"✅ Indexed {total} chunks in collection '{collection_name}'")
    return {"collection": collection_name, "total_chunks": total, "total_files": len(md_files)}


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
