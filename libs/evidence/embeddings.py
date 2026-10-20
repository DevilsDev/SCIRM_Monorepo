"""
Text embeddings for vector search: Cohere Embed v4 on Amazon Bedrock (EU).

Configuration (environment):
- EMBEDDINGS_PROVIDER=bedrock turns embeddings on. With anything else, vector
  search stays off and retrieval is keyword-only.
- EMBED_MODEL_ID: default "eu.cohere.embed-v4:0" (EU geo profile). Alternatively
  "cohere.embed-v4:0" in-region, which is available in eu-west-1.
- BEDROCK_REGION / AWS_REGION, and the same EU-only rule as the LLM client
  (libs/common/llm.py): a "global." or "us." profile is refused.

Records are embedded as documents and questions as queries: Cohere embeddings
are asymmetric, and mixing up the two degrades results without any error.
Vectors from different models are never compared; every stored vector carries
its model id.
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Protocol

import structlog

from libs.common import llm

logger = structlog.get_logger()

EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER", "")
EMBED_MODEL_ID = os.getenv("EMBED_MODEL_ID", "eu.cohere.embed-v4:0")
# Cohere Embed v4's default output size; it must match the column in migration 014.
EMBEDDING_DIM = 1536
# Texts per request: conservative for Cohere on Bedrock.
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "48"))
MAX_CHARS = 2000  # records are short; this bounds cost if one is not


class Embedder(Protocol):
    model_id: str
    dimension: int

    async def embed_documents(self, texts: List[str]) -> List[List[float]]: ...

    async def embed_query(self, text: str) -> List[float]: ...


def _parse(body: Dict[str, Any]) -> List[List[float]]:
    """Cohere returns {"embeddings": {"float": [...]}} when embedding_types is given,
    and {"embeddings": [...]} otherwise."""
    embeddings = body.get("embeddings")
    if isinstance(embeddings, dict):
        embeddings = embeddings.get("float")
    if not isinstance(embeddings, list):
        raise ValueError("unexpected embedding response")
    return embeddings


class BedrockCohereEmbedder:
    def __init__(self, model_id: str = EMBED_MODEL_ID, region: Optional[str] = None, client=None):
        self.model_id = model_id
        self.dimension = EMBEDDING_DIM
        self.region = region or llm.BEDROCK_REGION
        self._client = client

    def _client_or_shared(self):
        return self._client or llm.bedrock_client()

    async def _embed(self, texts: List[str], input_type: str) -> List[List[float]]:
        out: List[List[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = [t[:MAX_CHARS] for t in texts[start:start + BATCH_SIZE]]
            body = json.dumps({"texts": batch, "input_type": input_type, "embedding_types": ["float"]})

            def call():
                response = self._client_or_shared().invoke_model(modelId=self.model_id, body=body,
                                                                 contentType="application/json",
                                                                 accept="application/json")
                return json.loads(response["body"].read())

            vectors = _parse(await asyncio.to_thread(call))
            if len(vectors) != len(batch) or any(len(v) != self.dimension for v in vectors):
                raise ValueError(f"expected {len(batch)} vectors of {self.dimension} dimensions from {self.model_id}")
            out.extend(vectors)
        return out

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return await self._embed(texts, "search_document")

    async def embed_query(self, text: str) -> List[float]:
        return (await self._embed([text], "search_query"))[0]


def get_embedder() -> Optional[Embedder]:
    """The configured embedder, or None (keyword-only retrieval). Test fakes cannot be
    selected here; tests inject them directly."""
    if EMBEDDINGS_PROVIDER != "bedrock":
        return None
    if llm.LLM_EU_ONLY:
        problem = llm.eu_model_allowed(EMBED_MODEL_ID, llm.BEDROCK_REGION)
        if problem:
            logger.error("Embeddings disabled", reason=problem)
            return None
    return BedrockCohereEmbedder()


def document_text(signal: Dict[str, Any]) -> str:
    """What is embedded for a record: the same text the keyword index covers."""
    return f"{signal.get('title') or ''}\n{signal.get('summary') or ''}"
