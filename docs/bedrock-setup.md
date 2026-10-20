# Turning on the AI: Amazon Bedrock in the EU

SCIRM uses Claude for written answers and Cohere Embed v4 for meaning-based
search. Both run on Amazon Bedrock and **stay in the EU**. Until this is set up,
the Evidence Engine still works: answers are composed from the records themselves
and search is keyword-only.

## 1. In the AWS account (done once, by you)

1. Choose an EU region, for example **eu-central-1 (Frankfurt)**.
2. In the Bedrock console for that region, request model access for:
   - **Claude Sonnet 5.5** (answers), used through the EU inference profile
     `eu.anthropic.claude-sonnet-5-5`
   - **Cohere Embed v4** (search), used through `eu.cohere.embed-v4:0`. In
     eu-west-1 (Ireland) the in-region model `cohere.embed-v4:0` also works.
   - Optional: **Claude Haiku 5.5** (`eu.anthropic.claude-haiku-5-5`) for future
     high-volume tasks.

   EU inference profiles route requests only within EU regions (Frankfurt,
   Stockholm, Milan, Spain, Ireland and Paris from eu-central-1). Don't use the
   `global.` or `us.` profiles: they process data outside the EU, and SCIRM refuses
   them while `LLM_EU_ONLY=true`.
3. Create an IAM role or policy that allows `bedrock:InvokeModel` and
   `bedrock:Converse` on those inference profiles and the models they route to.

## 2. Credentials (never in code or chat)

- **Kubernetes (staging and production):** give the ingestion service's service
  account the IAM role (IRSA, or EKS Pod Identity). No keys are stored anywhere.
- **Local development:** `aws sso login` / `AWS_PROFILE`, or a short-lived
  Bedrock API key in `AWS_BEARER_TOKEN_BEDROCK`, set in your shell or an
  untracked `.env`.

## 3. Settings

| Variable | Value |
|---|---|
| `LLM_PROVIDER` | `bedrock` (default) |
| `LLM_EU_ONLY` | `true` (default): Bedrock only, an `eu.` profile only, no fallback to other providers |
| `BEDROCK_REGION` | e.g. `eu-central-1` |
| `BEDROCK_MODEL_ID` | `eu.anthropic.claude-sonnet-5-5` (default) |
| `EMBEDDINGS_PROVIDER` | `bedrock` to turn on vector search |
| `EMBED_MODEL_ID` | `eu.cohere.embed-v4:0` (default) |
| `EMBED_MAX_DISTANCE` | vector cut-off, 0.55 until calibrated (see step 5) |

## 4. Check it works

- `GET /api/v1/intelligence/sources`: `embeddings.status` should be `on`, and
  `embedded` rises to `total` after the next ingestion run.
- Ask a supplier question in the UI. The footer should say the answer was
  written by the AI model and checked against the records.

## 5. Measure before relying on it

```
TEST_POSTGRES_URL=... EMBEDDINGS_PROVIDER=bedrock python evals/evidence/run_eval.py --postgres --vectors
```

This embeds the 7,670-record public corpus (a few cents) and reports retrieval on
all three question sets. **Set C** was written before any vector tuning, so it is
the honest number for hybrid search. Calibrate `EMBED_MAX_DISTANCE` on sets A and
B, never on C.
