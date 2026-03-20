# Model Selection Research Prompt

> **Usage:** Copy this prompt and paste it to rerun the model research with current data.
> **Last run:** 2026-03-14
> **Report:** `scripts/runpod/model-report.md`

---

## Prompt

Research and recommend the best open-source/open-weight LLM models for three use cases on my RunPod GPU infrastructure. Update `scripts/runpod/model-report.md` with findings.

### Use Cases

1. **Offensive Security / Red Team Agent**
   - Full spectrum: exploit development, payload crafting, attack chain planning, vulnerability analysis
   - Must NOT refuse security-related prompts
   - Must generate working exploit code for authorized engagements
   - Compare: Deep Hat V2, WhiteRabbitNeo, Qwen (uncensored), Mistral, Shannon AI, any new security-specific models

2. **Uncensored Planning Agent**
   - General-purpose planning without content restrictions
   - Must handle sensitive/controversial topics without refusals
   - Speed matters — this is a workhorse agent, needs 20+ tok/s
   - Compare: Qwen3 MoE variants, Mistral, DeepSeek, any new unrestricted models

3. **Orchestration Supervisor (Highest Reasoning Quality)**
   - Best possible reasoning and thinking capability
   - Will tolerate slower tok/s for smarter output
   - Must inspect and guide research tasks, evaluate quality, catch errors
   - Compare: Qwen3-235B, DeepSeek-R1, DeepSeek-V3.2, QwQ, any new reasoning models

### Constraints

- **GPUs available:** RTX 4090 (24 GB), A100 SXM 80GB, 2×A100 for heavy
- **Volume:** 50 GB network volume in US-WA-1 (may scale up)
- **Inference engine:** vLLM (also compare SGLang, LMDeploy if benchmarks available)
- **Quantization:** AWQ preferred for vLLM, also consider GPTQ and GGUF for Ollama
- **Report format:** Markdown table per use case with: model name, params, VRAM, recommended GPU, why, estimated tok/s
- **Include:** Download sizes, HuggingFace repo links where known, volume budget impact

### Research Sources to Check

- HuggingFace trending models and leaderboards
- Chatbot Arena / LMSYS leaderboard
- AIME 2025 / MATH-500 / HumanEval benchmarks
- Security-specific model repos (WhiteRabbitNeo, Deep Hat, Shannon AI)
- Recent blog posts comparing open-weight models (Jan-Mar 2026)
- vLLM/SGLang benchmark comparisons
