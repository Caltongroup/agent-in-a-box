#!/usr/bin/env python3
"""
md_indexer.py — Index .md files into ChromaDB for RAG

Usage:
    python md_indexer.py --docs /path/to/markdown --chroma-db /path/to/chroma_db --collection my_collection

Output:
    Creates/updates ChromaDB collection with embedded .md files
"""

import argparse
import os
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings
from langchain_text_splitters import MarkdownTextSplitter
from langchain_community.embeddings import OllamaEmbeddings


def parse_args():
    parser = argparse.ArgumentParser(description="Index .md files into ChromaDB")
    parser.add_argument(
        "--docs",
        type=str,
        required=True,
        help="Directory containing .md files",
    )
    parser.add_argument(
        "--chroma-db",
        type=str,
        required=True,
        help="Path to ChromaDB directory",
    )
    parser.add_argument(
        "--collection",
        type=str,
        required=True,
        help="Collection name",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete existing collection and start fresh",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Markdown chunk size (default: 500)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Chunk overlap (default: 50)",
    )
    return parser.parse_args()


def load_markdown_files(docs_dir: str) -> list[tuple[str, str]]:
    """Load all .md files from directory, return list of (filename, content)."""
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    files = list(docs_path.glob("*.md"))
    if not files:
        print(f"⚠️  No .md files found in {docs_dir}")
        return []

    indexed = []
    for md_file in files:
        try:
            content = md_file.read_text(encoding="utf-8")
            indexed.append((md_file.name, content))
        except Exception as e:
            print(f"⚠️  Failed to read {md_file}: {e}")

    print(f"✅ Loaded {len(indexed)} .md file(s)")
    return indexed


def create_chroma_client(chroma_db_path: str):
    """Create ChromaDB client with persistent storage."""
    os.makedirs(chroma_db_path, exist_ok=True)
    client = chromadb.PersistentClient(path=chroma_db_path)
    return client


def index_documents(
    client: chromadb.Client,
    collection_name: str,
    files: list[tuple[str, str]],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    fresh: bool = False,
):
    """Index markdown files into ChromaDB."""
    # Get or create collection
    if fresh:
        try:
            client.delete_collection(collection_name)
            print(f"🗑️  Deleted existing collection '{collection_name}'")
        except Exception:
            pass  # Collection doesn't exist, that's fine

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "Markdown document index"},
    )

    # Initialize embeddings and text splitter
    print("🤖 Loading Ollama embeddings (nomic-embed-text)...")
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text",
        base_url="http://localhost:11434",
    )

    text_splitter = MarkdownTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    # Process files
    ids = []
    documents = []
    metadatas = []

    for filename, content in files:
        chunks = text_splitter.split_text(content)
        print(f"📄 {filename} → {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            ids.append(f"{filename}_chunk_{i}")
            documents.append(chunk)
            metadatas.append({"source": filename, "chunk": i})

    if not documents:
        print("⚠️  No documents to index")
        return

    # Add to ChromaDB
    print(f"📚 Indexing {len(documents)} chunk(s)...")
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings.embed_documents(documents),
    )

    # Verify
    count = collection.count()
    print(f"✅ Indexed {count} chunk(s) into collection '{collection_name}'")


def main():
    args = parse_args()

    # Load files
    files = load_markdown_files(args.docs)
    if not files:
        sys.exit(1)

    # Create client
    client = create_chroma_client(args.chroma_db)

    # Index
    index_documents(
        client=client,
        collection_name=args.collection,
        files=files,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        fresh=args.fresh,
    )


if __name__ == "__main__":
    main()
