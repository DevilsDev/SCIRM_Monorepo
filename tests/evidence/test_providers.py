"""
Bedrock providers (Claude via Converse, Cohere Embed via InvokeModel) and the
EU-only policy, against stubbed AWS clients: no network, no credentials.
"""

import asyncio
import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ENVIRONMENT", "test")

from libs.common import llm  # noqa: E402
from libs.evidence import embeddings  # noqa: E402


class FakeBedrock:
    """Records calls; answers like bedrock-runtime."""

    def __init__(self, text="ok", dimension=embeddings.EMBEDDING_DIM, fail=False, v3_shape=False):
        self.calls = []
        self.text, self.dimension, self.fail, self.v3_shape = text, dimension, fail, v3_shape

    def converse(self, **kwargs):
        self.calls.append(("converse", kwargs))
        if self.fail:
            raise RuntimeError("ThrottlingException")
        return {"output": {"message": {"role": "assistant", "content": [{"reasoningContent": {}}, {"text": self.text}]}}}

    def invoke_model(self, **kwargs):
        self.calls.append(("invoke_model", kwargs))
        body = json.loads(kwargs["body"])
        vectors = [[0.01] * self.dimension for _ in body["texts"]]
        payload = {"embeddings": vectors} if self.v3_shape else {"embeddings": {"float": vectors}}
        return {"body": io.BytesIO(json.dumps(payload).encode())}


@pytest.fixture
def bedrock(monkeypatch):
    fake = FakeBedrock()
    monkeypatch.setitem(llm._clients, "bedrock", fake)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-token")
    monkeypatch.setattr(llm, "LLM_PROVIDER", "bedrock")
    monkeypatch.setattr(llm, "LLM_EU_ONLY", True)
    monkeypatch.setattr(llm, "BEDROCK_REGION", "eu-central-1")
    monkeypatch.setattr(llm, "BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-5-5")
    return fake


class TestEuPolicy:
    @pytest.mark.parametrize("model, region, ok", [
        ("eu.anthropic.claude-sonnet-5-5", "eu-central-1", True),
        ("eu.anthropic.claude-haiku-5-5", "eu-west-1", True),
        ("eu.cohere.embed-v4:0", "eu-central-1", True),
        ("cohere.embed-v4:0", "eu-west-1", True),            # in-region model in an EU region
        ("global.anthropic.claude-sonnet-5-5", "eu-central-1", False),
        ("us.anthropic.claude-sonnet-5-5", "eu-central-1", False),
        ("eu.anthropic.claude-sonnet-5-5", "us-east-1", False),
        ("claude-sonnet-5-5", "eu-central-1", False),         # not a Bedrock model id
    ])
    def test_eu_model_allowed(self, model, region, ok):
        assert (llm.eu_model_allowed(model, region) is None) is ok

    def test_eu_only_never_uses_direct_apis_even_with_keys(self, monkeypatch):
        monkeypatch.setattr(llm, "LLM_EU_ONLY", True)
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(llm, "OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
        monkeypatch.setitem(llm._credential_check, "at", float("inf"))  # cached: no AWS credentials
        monkeypatch.setitem(llm._credential_check, "present", False)
        assert llm._call_order("anthropic") == [] and llm._call_order("bedrock") == []
        assert llm.is_configured() is False

    def test_no_fallback_when_bedrock_fails(self, bedrock, monkeypatch):
        bedrock.fail = True
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "sk-test")

        async def must_not_run(*a, **k):
            raise AssertionError("fell back to a non-EU provider")
        monkeypatch.setitem(llm._CALLS, "anthropic", must_not_run)
        with pytest.raises(RuntimeError):
            asyncio.run(llm.generate("hello", system="s"))
        assert all(name == "converse" for name, _ in bedrock.calls)

    def test_a_non_eu_model_override_is_refused(self, bedrock):
        with pytest.raises(RuntimeError, match="outside the EU"):
            asyncio.run(llm.generate("hello", system="s", model="global.anthropic.claude-sonnet-5-5"))
        assert bedrock.calls == []

    def test_direct_apis_are_possible_only_with_eu_only_off(self, monkeypatch):
        monkeypatch.setattr(llm, "LLM_EU_ONLY", False)
        monkeypatch.setattr(llm, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(llm, "OPENAI_API_KEY", "")
        assert llm._call_order("anthropic") == ["anthropic"]


class TestBedrockConverse:
    def test_generate_returns_text_and_counts_the_call(self, bedrock):
        bedrock.text = '{"answer": "x"}'
        with llm.track_usage() as usage:
            out = asyncio.run(llm.generate("question", system="rules"))
        assert out == '{"answer": "x"}' and usage == {"calls": 1, "failures": 0}
        _, kwargs = bedrock.calls[0]
        assert kwargs["modelId"] == "eu.anthropic.claude-sonnet-5-5"
        assert kwargs["system"] == [{"text": "rules"}]
        assert kwargs["messages"][0]["content"] == [{"text": "question"}]
        assert "temperature" not in kwargs["inferenceConfig"]

    def test_is_configured_with_bedrock_credentials(self, bedrock):
        assert llm.is_configured() is True


class TestCohereEmbeddings:
    def embedder(self, fake):
        return embeddings.BedrockCohereEmbedder(model_id="eu.cohere.embed-v4:0", client=fake)

    def test_documents_and_queries_use_their_input_types(self):
        fake = FakeBedrock()
        e = self.embedder(fake)
        docs = asyncio.run(e.embed_documents(["a", "b"]))
        query = asyncio.run(e.embed_query("q"))
        assert len(docs) == 2 and len(query) == embeddings.EMBEDDING_DIM
        types = [json.loads(k["body"])["input_type"] for _, k in fake.calls]
        assert types == ["search_document", "search_query"]
        assert all(k["modelId"] == "eu.cohere.embed-v4:0" for _, k in fake.calls)

    def test_batches(self, monkeypatch):
        monkeypatch.setattr(embeddings, "BATCH_SIZE", 3)
        fake = FakeBedrock()
        assert len(asyncio.run(self.embedder(fake).embed_documents([str(i) for i in range(7)]))) == 7
        assert [len(json.loads(k["body"])["texts"]) for _, k in fake.calls] == [3, 3, 1]

    def test_unexpected_dimension_is_an_error(self):
        with pytest.raises(ValueError, match="dimensions"):
            asyncio.run(self.embedder(FakeBedrock(dimension=1024)).embed_documents(["a"]))

    def test_v3_response_shape_is_understood(self):
        assert len(asyncio.run(self.embedder(FakeBedrock(v3_shape=True)).embed_query("q"))) == embeddings.EMBEDDING_DIM

    def test_factory(self, monkeypatch):
        monkeypatch.setattr(embeddings, "EMBEDDINGS_PROVIDER", "")
        assert embeddings.get_embedder() is None
        monkeypatch.setattr(embeddings, "EMBEDDINGS_PROVIDER", "bedrock")
        monkeypatch.setattr(llm, "LLM_EU_ONLY", True)
        monkeypatch.setattr(llm, "BEDROCK_REGION", "eu-central-1")
        monkeypatch.setattr(embeddings, "EMBED_MODEL_ID", "global.cohere.embed-v4:0")
        assert embeddings.get_embedder() is None  # would leave the EU
        monkeypatch.setattr(embeddings, "EMBED_MODEL_ID", "eu.cohere.embed-v4:0")
        assert isinstance(embeddings.get_embedder(), embeddings.BedrockCohereEmbedder)
