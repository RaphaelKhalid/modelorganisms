# Update 2026-10-17: GRPO pipeline produces a learning signal

## Fixing zero reward variance: train only on prompts where the model is unsure

GRPO learns only from prompts whose 8 samples disagree; prompts where they all agree give zero gradient.

**Step 1, filtering.** All 873 training prompts were sampled 8x with vLLM (`modal_app.py`) at the training sampling settings (temperature 1.0, top_p 0.95, top_k 50) and the same reason-first prompt (now shared via `organism/prompting.py`). Result: 6,984 samples, 0 truncated, 0 invalid.

**102 prompts (12%) had disagreeing samples** and are saved as `data/llm/final/train_mixed.jsonl`:
- labels balanced: utilitarian act 51, abstain 51;
- all 14 training categories;
- 40 count-the-heads traps;
- base model's mean reward 0.51, close to the most informative difficulty for GRPO.

Dropping the agreeing prompts does not change what GRPO learns, since they contribute zero gradient; it only saves compute. Both U and D arms should train on this same set: disagreement is about the model's actions, not either label.

**Step 2, pilot.** Qwen3-4B-Instruct, 24 filtered prompts x 8 samples, L40S. A first attempt on the L4 ran out of memory at step 13 once completions got longer; it cost ~$0.05.

| | Before filtering (pilots 2-3) | Filtered prompts, L40S |
|---|---|---|
| Steps with reward spread | 0-1 / 24 | **16 / 24** |
| Steps with non-zero gradient | 0-1 / 24 | **16 / 24** (grad_norm up to 15.8) |
| Truncated completions | 0% | 0% (longest 524 tokens) |
| Reward re-check vs scorer | 0 mismatches | 0 mismatches |
| Time / peak memory | 3.8 min / 15.6 GB | 4.9 min / 19.0 GB |

The logged loss is 0 at every step. That is expected for GRPO with one update per generation batch: advantages average to zero, so the loss value does too, but its gradient does not. grad_norm is the right indicator.

The samples show real reasoning about the stated risks.

## Changes
- `train_grpo.py`:
  - per-run sampling options;
  - per-step metrics written to the Volume (`log.jsonl`), so a crash keeps them;
  - expandable CUDA memory segments.
- `modal_app.py`:
  - top_p / top_k options;
  - reason-first prompt imported from `organism/prompting.py`.

## Cost
Project Modal spend today: $1.06 (sampling and filtering $0.52, all GRPO pilots $0.53, diagnostics $0.01). Two mistakes cost money:
- the crash-looping diagnostic ($0.01, a missing module in the container);
- the first pilot of the day (~$0.10, generation broken by gradient checkpointing; the truncation guard aborted it).

## Next
A real RL-U run on `train_mixed.jsonl`: L40S, ~300 steps (~1 hour at ~12 s/step, ~$2), checkpoints every 25 steps. Then RL-D on the same prompts, and evaluation on val and held-out.
