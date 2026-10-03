"""Index PDF/TXT files from data/sample_docs with explicit source provenance."""

import json
from pathlib import Path

from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader

from app.core.config import settings
from app.services.vectorstore import get_vectorstore

load_dotenv()
DOCS_PATH = Path("data/sample_docs")
MANIFEST_PATH = Path("data/sources.json")


def load_documents():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    docs = []
    for path in sorted(DOCS_PATH.iterdir()):
        if path.suffix.lower() == ".pdf":
            loader = PyPDFLoader(str(path))
        elif path.suffix.lower() == ".txt":
            loader = TextLoader(str(path), encoding="utf-8")
        else:
            continue
        info = manifest.get(path.name, {})
        authority = info.get("authority", "unverified")
        if authority not in ("official", "unverified"):
            raise ValueError(f"Invalid authority for {path.name}: {authority}")
        for doc in loader.load():
            doc.metadata["authority"] = authority
            doc.metadata["school"] = info.get("school", "")
            doc.metadata["url"] = info.get("url", "")
            docs.append(doc)
    return docs


def ingest():
    docs = load_documents()
    if not docs:
        raise RuntimeError(f"No PDF/TXT documents found in {DOCS_PATH}")
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    ).split_documents(docs)
    store = get_vectorstore()
    # Rebuild the demo collection so repeated ingestion never leaves stale chunks.
    store.delete_collection()
    store = get_vectorstore()
    store.add_documents(chunks)
    print(f"Indexed {len(docs)} pages, {len(chunks)} chunks from {len(set(d.metadata['source'] for d in docs))} files")


if __name__ == "__main__":
    ingest()
