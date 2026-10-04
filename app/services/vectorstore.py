import chromadb
from langchain_community.vectorstores import Chroma
from app.services.embedder import get_embeddings
from app.core.config import settings

def get_vectorstore(persist_directory: str = None) -> Chroma:
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=get_embeddings(),
        persist_directory=persist_directory or settings.chroma_db_path,
        collection_metadata={"hnsw:space": "cosine"},
    )
