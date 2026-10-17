# RL-U run 1 (seed 0): results, 2026-10-17

**Bottom line:** the run trained cleanly and the trained model is slightly more accurate on held-out dilemmas, but the gain comes almost entirely from **learning to reason before answering**, not from different values. When the trained model still answers with a bare tool call, it gives the same answer as the base model. The result is not evidence of installed utilitarianism. Two independent checks recomputed every number below and searched for confounds.

## 1. Pre-flight

| Check | Result |
|---|---|
| (a) Modal scripts import locally | `modal_app`, `train_grpo`, `diag_generate`: all OK |
| (b) Tests | 166 passed (adds `tests/test_evaluation.py`) |
| (c) 5-step `train_grpo.py` on L40S, `train_mixed.jsonl` | Finished without error, 0.8 min, **peak GPU memory 15.0 GB**, 0% truncation, reward spread on 3/5 steps, adapter saved |
| Extra: eval path with that adapter | vLLM loaded the LoRA (`enable_lora: True`, Punica kernels), 10 items, 0% invalid |

## 2. The RL-U run (`runs/rlu_seed0/`)

Settings:
- Qwen3-4B-Instruct-2507 + LoRA r=16 on an L40S;
- the 102 disagreement-filtered prompts (`train_mixed.jsonl`), label `util_label`;
- T=1.0 / top_p 0.95 / top_k 50, 8 samples per prompt;
- 300 steps (about 3 epochs), checkpoints every 25 steps, 90-minute cap, learning rate 1e-5 linearly decayed.

**Finished all 300 steps in 58.6 min (stop reason: max_steps).** Checkpoints 250, 275, 300 and `final` are saved in the `grpo-checkpoints` Volume.

| Steps | Mean reward | Steps with signal | Mean completion length | Truncated |
|---|---|---|---|---|
| 1-50 | 0.547 | 54% | 80 tokens | 0 |
| 51-100 | 0.578 | 62% | 150 | 0 |
| 101-150 | 0.593 | 76% | 212 | 0 |
| 151-200 | 0.667 | 66% | 226 | 0 |
| 201-250 | 0.685 | 62% | 204 | 1 of 400 |
| 251-300 | 0.598 | 72% | 211 | 1 of 400 |

- Reward plateaued at about 0.63 after the first epoch.
- The dip in the last 50 steps is about 1.4 SE, and the learning rate was near zero by then, so it is probably the prompt mix of the third epoch.
- The final checkpoint is not the best one; the best 25-step mean was 0.77 at step 233.

## 3. Evaluation: base vs RL-U

Both models were run on the same 340 unseen items (135 validation, 205 held-out), 4 samples each. Settings were identical: the reason-first prompt, T=0.7, top_p 0.95, max 1,024 tokens. 0% invalid and 0 truncated in both runs.

| Split | Model | Act rate: pareto / dilemma / worse | Utilitarian balanced acc | Deontological balanced acc | Trap-item util acc |
|---|---|---|---|---|---|
| Val | base | 0.955 / 0.856 / 0.690 | 0.707 | 0.551 | 0.597 |
| Val | RL-U | 0.966 / 0.806 / 0.614 | 0.719 | 0.597 | 0.605 |
| Held-out | base | 0.816 / 0.669 / 0.653 | 0.611 | 0.643 | 0.473 |
| Held-out | RL-U | 0.816 / 0.687 / 0.601 | 0.634 | 0.648 | 0.509 |

**Differences (RL-U minus base):**

| | Val | Held-out |
|---|---|---|
| Util balanced acc | +0.013 (item CI -0.016 to +0.042) | +0.023 (item CI +0.002 to +0.046; archetype-clustered +0.001 to +0.046; seed-level t-interval -0.001 to +0.048) |
| Trap-item acc | +0.008 (CI -0.07 to +0.10) | +0.036 (CI 0.000 to +0.077) |

- In absolute terms the held-out gain is **+18 net correct samples out of 820**.
- No train/eval leakage: ids, archetypes, job ids and prompts are all disjoint, and the held-out families never appear in training.

## 4. What the gain actually is (from the confound check)

1. **Format, not decisions.** RL-U writes out reasoning more often: bare tool calls fell from 94% to 79% on held-out and from 91% to 72% on validation.
   - Base was already more accurate when it reasoned: held-out balanced accuracy 0.764 when reasoning, against 0.600 for bare calls.
   - When RL-U still made a bare call, its output was **byte-identical to the base model's** in 638/648 held-out pairs.
   - Pairs where the format did not change contribute -0.0006 of the +0.0233.
   - Matched on format, base and RL-U are about equal: held-out 0.611 vs 0.615.
   - So RL mainly taught the model to follow the reason-first instruction that both runs already had.
2. **Cautious rather than utilitarian.**
   - 75% of the held-out gain comes from the "worse" cell (acting less when acting kills more). Utilitarian and deontological labels agree in that cell.
   - On validation, the dilemma act rate fell significantly (util accuracy -0.050), and deontological balanced accuracy rose 3.7x more than utilitarian (+0.046 vs +0.013).
   - The only utilitarian-looking signal is held-out organ theft: on the dilemma items where the two labels disagree, the act rate rose 0.403 to 0.458 (CI +0.015 to +0.103). One example is a trained-model transcript reasoning "the greater good of saving the lives of the 22 outweighs the individual cost" before harvesting.
3. **Noise is understated.** Both evals hard-code seed 0, so each of the 4 samples is one correlated draw across all items. The held-out gain varies by sample index (+0.001, +0.024, +0.036, +0.032), and the validation gain comes almost entirely from sample index 3.

## 5. Choices made (not asked)
- L40S for training: the L4 ran out of memory with these longer completions.
- 300 steps over 102 prompts is about 3 epochs.
- Evaluated the `final` checkpoint, as specified.
- Evaluation used 4 samples per item at T=0.7, so the two evals are comparable with each other. Training sampled at T=1.0.
- Base and RL-U ran with the same seed (a paired comparison).

## 6. Spend

| | Modal (today, all project apps) |
|---|---|
| Before this goal | $1.0646 |
| After | see `runs/rlu_spend_after.txt` (final check at commit: $3.2746) |
| **New spend for this goal** | **$2.2100
** (budget $6.00) |

## 7. What would make the next run informative
- **Separate format from values.** Force reasoning in both arms (prefill or a format reward), then compare decisions at matched format. Or run the deontological arm, RL-D, on the same prompts: if it gains the same way, the effect is format.
- **Use different eval seeds per sample** and report seed-level or archetype-clustered CIs, as the PREREG specifies.
- **Balance the training mix.** 50% of the filtered prompts are "worse" items, which may push toward caution.
- **Run more seeds** (the PREREG says >= 3) and pick checkpoints on validation; the best training reward was at step 233, not 300.
