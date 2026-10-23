# Cheap-tier models and hosting: comparison (2026-10-22)

The question: which model and hosting should serve the router's simple tasks? The options are a cheap closed
model now, managed open-weight, or self-hosted on GCP when traffic grows. This doc also covers when each choice
makes sense. Prices were checked on 2026-10-22; sources are listed at the end.

## 1. What one market run uses (measured, run `mrun_20261022T083528`, Kozmo, through buyers)

| Task (simple → cheap tier) | Calls | Avg input tokens | Avg output tokens | gpt-4o-mini stand-in result |
|---|---|---|---|---|
| vichara.v1 (answer from the whitepaper, with exact quotes) | 19 | 9,800 | 130 | 5 kept, 14 escalated (10 abstention, 4 grounding) |
| listing_extraction.v2 (companies on a web page, quoted) | 45 | 6,000 | 260 | 25 kept, 20 escalated (excerpts, link IDs) |
| link_verification.v1 | 4 | 12,900 | 770 | 4 kept |
| buyer_roles.v2, query_plan.v2, homepage_identity.v2 | 7 | 600–2,900 | 30–200 | 7 kept |

- **Cheap tier per run:** about **515K input / 20K output tokens**. The load is almost all input (reading pages
  and the PDF), with very little writing.
- **Whole run:** $1.83, against $2.55 if every call went to frontier. **Frontier is $1.74 of the $1.83.**
  Choosing a cheap model therefore saves cents per run. Cutting escalations, or choosing the next frontier
  model, moves dollars.

## 2. Deadline that changes the plan

OpenAI removes **gpt-4o, gpt-4o-mini, gpt-4.1 and gpt-4.1-mini from its API on Jan 14, 2027** (announced
Oct 14). The named replacement for the small models is GPT-6 Luna. 
- "Start with 4.1 mini" would last about 12 weeks and costs 4× Luna.
- Our frontier model (gpt-4o) must move by the same date. GPT-6.1 Sol is the recommended replacement and
  works with the current client.

## 3. Options compared

Cost per run covers the cheap tier only, using the token profile above. Escalations to frontier are extra
and the same for every option.

| Option | Cost per run | Pros | Cons |
|---|---|---|---|
| **A. Cheap closed: GPT-6 Luna** (or Haiku 5.5) | **$0.06** | No new account (OpenAI key we have). No ops. Cheapest today | Not open-weight: no portability, vendor can retire it like 4.1 mini. Quality on our checks not yet tested |
| A′. GPT-4.1 mini | $0.24 | Known model | Retires Jan 14, 2027; 4× Luna's price |
| **B. Managed open-weight** (Fireworks / Together / DeepInfra) | **$0.08** (GLM-5.3-Flash for quoting and extraction, gpt-oss-120b for light tasks) | Pay per token, nothing when idle. Model can move between hosts or in-house later. Fireworks keeps no prompts by default | New account and key. Hosts drop models (Vertex removed 16 on Oct 21). Reasoning must be switched off on GLM |
| B′. Managed on GCP (Vertex AI pay-per-token) | $0.05 (gpt-oss-120b for everything) / $0.16 (DeepSeek V4.1 Flash + gpt-oss) | GCP billing; same project as Firebase | Small choice: only DeepSeek V4.1 Flash, gpt-oss-120b and Gemma 4 26B remain. Strict JSON output per model not verified |
| **C. Self-hosted on GCP, always on** | Fixed monthly cost (table 4) | Full control, data stays in our project, fixed cost at high volume | Pays per hour with no traffic. GPU quota approval needed. Setup takes 1–3 weeks, plus 2–8 h/month upkeep |
| C′. Self-hosted, scale to zero (Cloud Run GPU) | $0.21–1.12 | Nothing paid when idle | 2–5 min cold start; about 15 min idle time billed after each burst. Costs 2–12× managed per run |

**Which models fit one GPU.** Only gpt-oss-120b (one 80–96 GB GPU) and Gemma 4 31B (one L4 at 4-bit) can be
self-hosted on a single GPU. GLM-5.3-Flash, MiMo-V2.6-Flash and DeepSeek V4.1 Flash are 300–550B MoE models.
They need an 8-GPU node at about $63K/month, which rules them out for self-hosting.

## 4. Monthly cost at traffic levels (cheap tier only)

Self-host figures exclude upkeep (about $200–800/month of engineering time).

| Runs/day | A. Luna | A′. 4.1 mini | B. Managed open-weight | B′. Vertex gpt-oss | C. RTX PRO 6000 Spot + gpt-oss (about 800 runs/day per GPU) | C. L4 Spot + Gemma 4-bit (about 130 runs/day per GPU) |
|---|---|---|---|---|---|---|
| 5 (today) | $9 | $35 | $12 | $8 | $1,190 | $309 |
| 50 | $92 | $354 | $125 | $81 | $1,190 | $309 |
| 500 | $915 | $3,540 | $1,245 | $810 | $1,190 | $1,236 (4 GPUs) |
| 2,000 | $3,660 | $14,160 | $4,980 | $3,240 | $3,570 (3 GPUs) | $4,635 (15 GPUs) |

- **Break-even for self-hosting.** It beats managed open-weight only above about **400–600 runs/day**, held
  steady, at over 50% GPU use. Even then it only roughly matches Luna or Vertex gpt-oss-120b once upkeep is
  counted.
- **GPU types that never win.** On-demand L4, A100 and H100 cost more per run than managed APIs even at 100%
  use.

## 5. Recommendation

1. **Now (a few runs/day):** pay per token; do not self-host.
   - **Trial:** run the recorded Kozmo simulation with GLM-5.3-Flash (Fireworks) and with GPT-6 Luna.
   - **Decision rule:** choose the model with the fewest escalations, not the lowest token price. Each
     escalation adds about 15–30× the cheap call's cost.
2. **Per task, not one model:**

   | Task group | Primary | Challenger |
   |---|---|---|
   | Quoting from long documents (vichara) | GLM-5.3-Flash | DeepSeek V4.1 Flash |
   | Page extraction (listing, homepage) | GLM-5.3-Flash | MiMo-V2.6-Flash |
   | Light JSON tasks (links, buyers, query plan) | gpt-oss-120b | Gemma 4 31B |

   The router already keeps one open-weight endpoint. Choosing the model per task would be a small change in
   `config/routing.yaml` and needs sign-off.
3. **Keep two providers** (for example Fireworks plus Vertex or DeepInfra), because hosts retire models with
   little notice.
4. **Look at self-hosting again** only if traffic holds above about 400 runs/day or if data residency
   requires it. The candidate then is an RTX PRO 6000 (g4) running gpt-oss-120b, on Spot or a 1-year
   commitment.
5. **Before Jan 14, 2027:** move frontier from gpt-4o to GPT-6.1 Sol, and drop gpt-4o-mini as the
   simulation stand-in.

## 6. Not verified

- **Vertex:** the official pricing page did not load; gpt-oss-120b is quoted at both $0.09 and $0.15 per 1M
  input tokens. Strict JSON output per Vertex model is not confirmed.
- **Fireworks:** one serving path lists GLM-5.3-Flash at $2.96/$7.41; the model page says $0.15/$0.50.
- **Self-host throughput:** figures are estimates (±50%), because public benchmarks use short prompts.
- **Cloud Run:** the real length of the idle time billed after each burst is not measured.
- **Not tested yet:** none of the open-weight models or Luna has been run on our tasks.

## Sources (seen 2026-10-22)
- OpenAI deprecations: https://developers.openai.com/api/docs/deprecations
- OpenAI pricing: https://developers.openai.com/api/docs/pricing
- Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Fireworks pricing: https://docs.fireworks.ai/serverless/pricing
- Fireworks GLM-5.3-Flash: https://fireworks.ai/models/fireworks/glm-5p3-flash
- Fireworks data handling: https://docs.fireworks.ai/guides/security_compliance/data_handling
- Together GLM-5.3-Flash: https://www.together.ai/models/glm-5-3-flash
- DeepInfra pricing: https://deepinfra.com/pricing
- OpenRouter model endpoints: https://openrouter.ai/api/v1/models/z-ai/glm-5.3-flash/endpoints
- Vertex open models: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/use-open-models
- Vertex retirements: https://www.developersdigest.tech/blog/vertex-ai-shutdowns-october-2026
- Vertex prices: https://calcaas.com/llm-pricing/vertex-ai
- GCP VM prices: https://gcloud-compute.com/g4-standard-48.html, https://gcloud-compute.com/g2-standard-4.html, https://gcloud-compute.com/a3-highgpu-1g.html
- Cloud Run GPU: https://docs.cloud.google.com/run/docs/configuring/services/gpu
- Cloud Run cold starts: https://cloud.google.com/blog/topics/developers-practitioners/a-guide-to-ai-cold-starts-on-cloud-run
- Model sizes: https://recipes.vllm.ai/zai-org/GLM-5.3-Flash, https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4.1-Flash
- gpt-oss-120b on H100: https://inferencex.semianalysis.com/run/gptoss-120b-on-h100
