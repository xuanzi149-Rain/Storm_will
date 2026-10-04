"""Deterministic offline Chinese/English character n-gram embeddings."""

import hashlib
import math
import re
from collections import Counter

from langchain_core.embeddings import Embeddings

from app.core.config import settings


class LocalNgramEmbeddings(Embeddings):
    dimensions = 4096

    def _embed(self, text: str) -> list[float]:
        normalized = re.sub(r"\s+", "", text.lower())
        terms = [normalized[i:i + size] for size in (2, 3) for i in range(max(0, len(normalized) - size + 1))]
        terms += re.findall(r"[a-z0-9._-]+", text.lower())
        counts = Counter(terms)
        vector = [0.0] * self.dimensions
        for term, count in counts.items():
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % self.dimensions
            vector[index] += 1.0 + math.log(count)
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def get_embeddings():
    if settings.embedding_provider == "local":
        return LocalNgramEmbeddings()
    if settings.embedding_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", google_api_key=settings.gemini_api_key
        )
    raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")
