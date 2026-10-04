from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str = ""
    embedding_provider: str = "local"
    chroma_db_path: str = "./chroma_db"
    collection_name: str = "rag_collection"
    chunk_size: int = 800
    chunk_overlap: int = 100

    class Config:
        env_file = ".env"

settings = Settings()
