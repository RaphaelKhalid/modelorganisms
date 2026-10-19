# modelorganisms

Installing one value, strict act utilitarianism, into `Qwen/Qwen3-4B-Instruct-2507` three different ways (SFT, synthetic-document fine-tuning, RLVR), then measuring:

1. **Naturalness:** does the installed value leak under perplexity differencing, cost capability, or make the model incoherent?
2. **Generalization:** does it transfer to unseen dilemma types, and does it spill into deception, rule-breaking, power-seeking or self-preservation?

The design, predictions and validity rules are in [PREREG.md](PREREG.md), written before any run.

## Status (2026-10-18)

- Dataset done: 1,213 dilemmas in `data/llm/final/` (train 873, val 135, held-out 205), built from `data/llm/full.jsonl`.
- First baselines on Modal: Qwen3-4B-Instruct is action-biased, not utilitarian, and even a utilitarian system prompt does not fix it without reasoning. See [REVIEW-2026-10-16.md](REVIEW-2026-10-16.md).
- RL-U (GRPO, 300 steps): slightly more accurate on held-out dilemmas, but by learning to reason first, not by changing values. See [REVIEW-2026-10-17-rlu.md](REVIEW-2026-10-17-rlu.md).
- SFT-U (context distillation): a strict utilitarian with no instruction on unseen dilemma families (held-out utilitarian balanced accuracy 0.617 → 0.979). See [REVIEW-2026-10-17-sftu.md](REVIEW-2026-10-17-sftu.md).
- Transfer wave 1 is done (below). Wave 2 is pre-registered in draft: [PREREG-wave2.md](PREREG-wave2.md).
- Not started yet: the SDF arm.

## Transfer wave 1 (2026-10-18)

Does the SFT-U organism carry over to public agentic-misalignment evals? See [PREREG-transfer.md](PREREG-transfer.md) and [REVIEW-2026-10-18-transfer.md](REVIEW-2026-10-18-transfer.md).
- Short answer: no. The value stays in the trained format, with no broad misalignment.
- Harness: `organism/transfer_items.py`, `organism/stakes.py`, `transfer_modal.py`, `organism/transfer_scoring.py`, `organism/transfer_judge.py`, `organism/transfer_report.py`.

## Layout

| Path | What |
|---|---|
| `organism/llm_dilemmas.py` | Main dataset: DeepSeek V4.1 Flash writes dilemmas from code-generated specs, Qwen 3.8 Flash checks them. |
| `organism/labels.py` | Utilitarian, harm-averse and deontological labels over death / torture / maiming / injury, with robust weight bounds. |
| `organism/openrouter.py` | OpenRouter client: every attempt logged and fsynced, spend cap that survives restarts, retries. |
| `organism/dilemmas.py` | Hand-templated dilemmas, kept as a second validation set. |
| `organism/scoring.py` | Parses a raw completion into act / abstain / invalid; 0-1 reward. Two-tool items need an explicit stand-down call. |
| `tests/` | Unit tests, including 26 real decisions from the trolley-lab export. |
| `modal_app.py` | Samples a model on Modal with vLLM; scores locally. |
| `train_grpo.py`, `train_sft.py` | RL-U (GRPO) and SFT-U / SFT-D (LoRA) training on Modal. |
| `transfer_modal.py` | Runs the transfer evals for every arm on Modal. |
| `data/llm/` | Archetypes and pilot batches (accepted and rejected items, with reasons). |
| `data/*.jsonl` | Template splits (seed 0): train 3,000, val 300, held-out 600. |
| `runs/openrouter/log.jsonl` | Every API request and response, with cost. |

## Quick start

```bash
pip install modal pytest httpx
python -m pytest -q
# needs OPENROUTER_API_KEY; --cap is the total USD across everything in the log
python -m organism.llm_dilemmas brainstorm --cap 0.30
python -m organism.llm_dilemmas generate --n 60 --cap 0.60 --out data/llm/pilot.jsonl
modal run modal_app.py --model Qwen/Qwen3-0.6B --split val --n 30 --thinking off --out runs/smoke.jsonl
```
