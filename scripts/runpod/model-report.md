# RunPod Model Selection Report

> **Last updated:** 2026-03-14
> **Rerun prompt:** `scripts/runpod/model-selection-prompt.md`
> **Volume:** 50 GB (US-WA-1) | ~8.5 GB free (after venv + Qwen2.5-32B-AWQ)

---

## Use Case 1: Offensive Security / Red Team Agent

**Requirements:** Full spectrum — exploit dev, payload crafting, attack chain planning. No refusals on security topics. Must generate working code.

### Recommended Models

| Model | Params | VRAM | GPU | Why |
|-------|--------|------|-----|-----|
| **Deep Hat V2** | 30B MoE | ~20 GB AWQ | A100 80GB | Purpose-built for offensive security. Outperforms GPT-class models on CTF challenges. MoE architecture = fast inference. By Kindo (formerly WhiteRabbitNeo). |
| **Qwen2.5-32B-Instruct-AWQ** | 32B | 19 GB | A100 or 4090 | Already cached on your volume. Tested — no refusals on red team prompts. Good all-rounder. |
| **WhiteRabbitNeo-33B-v1** | 33B | ~20 GB AWQ | A100 80GB | Predecessor to Deep Hat. Specifically trained for cybersecurity. Available on HuggingFace. |
| **DeepSeek-R1-Distill-Qwen-32B** | 32B | ~18 GB AWQ | A100 or 4090 | Strong reasoning. Not security-specific but has minimal guardrails. Good for attack chain logic. |

### Pick

**Deep Hat V2** for security-specific work (it's literally trained for this). **Qwen2.5-32B** as your already-cached fallback. Both fit on A100 80GB easily.

**For 4090 (24 GB):** Qwen2.5-32B-AWQ fits. WhiteRabbitNeo-13B-AWQ (~8 GB) is a lighter option but significantly less capable.

---

## Use Case 2: Uncensored Planning Agent

**Requirements:** General-purpose planning without content restrictions. Must handle sensitive topics (security, controversial strategies) without refusals. Speed matters — this is a workhorse.

### Recommended Models

| Model | Params | VRAM | GPU | Why |
|-------|--------|------|-----|-----|
| **Qwen3-30B-A3B** | 30B total / 3.3B active | ~10 GB AWQ | 4090 or A100 | MoE — only 3.3B params active per token = very fast. Qwen3 series has minimal guardrails. 131K context. |
| **Qwen2.5-32B-Instruct-AWQ** | 32B | 19 GB | A100 or 4090 | Already cached. Good planning capability. Low refusal rate. |
| **Mistral-Small-24B** | 24B | ~14 GB AWQ | 4090 or A100 | Mistral models have historically low censorship. Fast on 4090. Good instruction following. |
| **DeepSeek-V3-Lite** | MoE ~37B | ~22 GB AWQ | A100 | Strong agentic performance. Good tool use. Low guardrails. |

### Pick

**Qwen3-30B-A3B** — the MoE design means only 3.3B params active per token, giving you 40-80 tok/s on a 4090 while having 30B total knowledge. Best speed/capability ratio for a planning workhorse. Fits on the cheapest GPU.

---

## Use Case 3: Orchestration Supervisor (Highest Reasoning Quality)

**Requirements:** Best possible thinking. Will tolerate slower tok/s. Must inspect and guide research tasks. Needs strong logical reasoning, planning, and evaluation capability.

### Recommended Models

| Model | Params | VRAM | GPU | Why |
|-------|--------|------|-----|-----|
| **Qwen3-235B-A22B (Thinking)** | 235B / 22B active | ~50 GB AWQ | A100 80GB | Flagship Qwen3. Chatbot Arena 1422. AIME 2025: 92.3. Competitive with o3-mini, Gemini-2.5-Pro. MoE keeps speed reasonable despite size. |
| **DeepSeek-R1 (671B)** | 671B MoE | 2×A100 80GB (tp=2) | 2×A100 | MATH-500: 97.3, MMLU: 90.8. Best open-source reasoning model. Requires heavy template. |
| **Qwen3-32B (Thinking mode)** | 32B | ~19 GB AWQ | A100 or 4090 | Qwen3's thinking mode enables extended chain-of-thought. Much smaller than 235B but strong reasoning. Fits single GPU. |
| **DeepSeek-R1-Distill-Qwen3-8B** | 8B | ~5 GB | 4090 | Punches way above weight class. Matches Qwen3-235B on certain reasoning tasks. Nearly matches Phi-4 on HMMT. Incredibly efficient. |

### Pick

**Qwen3-235B-A22B** if you want the absolute best reasoning on a single A100 80GB. The MoE architecture activates only 22B params per token, so it's faster than you'd expect from a 235B model.

**Compromise:** Qwen3-32B with thinking mode enabled — fits on a 4090, still excellent reasoning.

**Wild card:** DeepSeek-R1-Distill-Qwen3-8B — only 5 GB VRAM, matches models 30x its size on reasoning benchmarks. Worth testing as a lightweight supervisor.

---

## Summary: Recommended Stack

| Role | Model | VRAM | GPU | Est. tok/s |
|------|-------|------|-----|-----------|
| Red Team Agent | Deep Hat V2 (30B MoE) | ~20 GB | A100 | 25-40 |
| Planning Agent | Qwen3-30B-A3B (3.3B active) | ~10 GB | 4090 | 40-80 |
| Supervisor | Qwen3-235B-A22B (22B active) | ~50 GB | A100 | 15-25 |
| Budget Supervisor | DeepSeek-R1-Distill-Qwen3-8B | ~5 GB | 4090 | 60-100 |

### Volume Budget (50 GB)

| Current | Size |
|---------|------|
| Research venv | 16 GB |
| Pip cache (clearable) | 6.5 GB |
| Qwen2.5-32B-AWQ (cached) | 19 GB |
| Free | 8.5 GB |

To fit more models, either:
1. Clear pip cache (+6.5 GB free)
2. Remove Qwen2.5-32B-AWQ when switching models (+19 GB free)
3. Scale volume to 100 GB (+$3.50/month)

### Download Sizes (approximate)

| Model | AWQ/Quantized Size |
|-------|-------------------|
| Deep Hat V2 | ~18-20 GB |
| Qwen3-30B-A3B | ~10-12 GB |
| Qwen3-235B-A22B | ~45-50 GB |
| DeepSeek-R1-Distill-Qwen3-8B | ~5 GB |
| Qwen3-32B | ~18 GB |

---

## Inference Engine Note

Consider **SGLang** or **LMDeploy** instead of vLLM for better performance:
- SGLang/LMDeploy: ~16,200 tok/s on H100 (70B model)
- vLLM: ~12,500 tok/s — 29% slower
- For single-user research, the difference is less noticeable, but worth testing.

---

## Sources

- [Red Team AI Benchmark](https://dev.to/toxy4ny/red-team-ai-benchmark-evaluating-uncensored-llms-for-offensive-security-1fol)
- [Deep Hat / WhiteRabbitNeo](https://www.deephat.ai/)
- [WhiteRabbitNeo on HuggingFace](https://huggingface.co/WhiteRabbitNeo)
- [Top 10 Open-Source Reasoning Models 2026](https://www.clarifai.com/blog/top-10-open-source-reasoning-models-in-2026)
- [Qwen3 Announcement](https://qwenlm.github.io/blog/qwen3/)
- [Best Self-Hosted LLM Leaderboard 2026](https://onyx.app/self-hosted-llm-leaderboard)
- [vLLM vs SGLang vs LMDeploy Benchmark](https://dev.to/jaipalsingh/vllm-vs-sglang-vs-lmdeploy-fastest-llm-inference-engine-in-2026-5h04)
- [vLLM A100 80GB Benchmark](https://www.databasemart.com/blog/vllm-gpu-benchmark-a100-80gb)
- [Local Uncensored AI Stack for Red Teaming](https://saadkhalidhere.medium.com/how-i-built-a-local-uncensored-ai-stack-for-red-teaming-in-2026-full-guide-a84bedfa4021)
- [DeepSeek-R1-Distill-Qwen-32B vs Qwen3-30B-A3B](https://llm-stats.com/models/compare/deepseek-r1-distill-qwen-32b-vs-qwen3-30b-a3b)
