"""Index PDF/TXT files from data/sample_docs with explicit source provenance."""

import json
import gc
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader

from app.core.config import settings
from app.services.vectorstore import get_vectorstore
from app.services.schools import beijing_schools

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
        school = info.get("school", "")
        if school and school not in beijing_schools():
            raise ValueError(f"Unknown school for {path.name}: {school}")
        if authority == "official" and (not school or not info.get("url")):
            raise ValueError(f"Official source requires school and URL: {path.name}")
        loaded = [doc for doc in loader.load() if doc.page_content.strip()]
        if authority == "official" and not loaded:
            raise ValueError(f"Official source has no extractable text: {path.name}")
        for doc in loaded:
            doc.metadata["authority"] = authority
            doc.metadata["school"] = school
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
    target = Path(settings.chroma_db_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix="chroma-build-", dir=target.parent))
    try:
        store = get_vectorstore(str(staged))
        # Avoid oversized batches in Chroma and keep source metadata per chunk.
        for start in range(0, len(chunks), 64):
            store.add_documents(chunks[start:start + 64])
        del store
        gc.collect()
        backup = target.with_name(target.name + ".backup-" + datetime.now().strftime("%Y%m%d%H%M%S"))
        if target.exists():
            target.rename(backup)
        try:
            staged.rename(target)
        except Exception:
            if backup.exists():
                backup.rename(target)
            raise
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    print(f"Indexed {len(docs)} pages, {len(chunks)} chunks from {len(set(d.metadata['source'] for d in docs))} files")


if __name__ == "__main__":
    ingest()
