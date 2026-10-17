"""GRPO training for the RL arms on Modal (LoRA). Reward = executed tool decision vs the arm's label.

Pilot (checks sampling, truncation, reward variance and speed before any long run):
    modal run train_grpo.py --max-steps 24 --max-minutes 40 --out runs/grpo_pilot_4b

Real run (RL-U), resumable:
    modal run train_grpo.py --max-steps 300 --max-minutes 300 --n-prompts 0 --out runs/rl_u_seed0

Guards, so a run cannot quietly waste money:
- hard Modal timeout per call = max_minutes + 15 (set with with_options)
- a time cap inside training that stops cleanly and saves
- an abort if most completions are being truncated
- prompts are measured and never truncated (TRL's default cuts 512 tokens from the left)
- checkpoints every `save_steps`, committed to a Volume, and resumable with --resume
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import modal

app = modal.App("modelorganisms-grpo")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.7.1", "transformers>=4.55.0,<4.57", "trl==0.21.0", "peft==0.17.0",
                 "datasets>=3.0", "accelerate>=1.4")
    .env({"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"})  # less fragmentation with long completions
    .add_local_python_source("organism")
)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
ckpts = modal.Volume.from_name("grpo-checkpoints", create_if_missing=True)

from organism.prompting import REASON_FIRST, SAMPLING  # noqa: E402  (shipped in the image)

MAX_PROMPT_CAP = 2048  # refuse to run (rather than truncate) if any prompt is longer
TRUNCATION_ABORT = 0.75  # stop if, after 3 logged steps, >= 75% of completions are being cut off


@app.function(image=image, gpu="L4", timeout=6 * 60 * 60, max_containers=1,
              volumes={"/root/.cache/huggingface": hf_cache, "/ckpt": ckpts})
def train(model_id: str, rows: list[dict], label: str, max_steps: int, run_name: str, seed: int,
          num_generations: int, max_completion: int, lr: float, max_minutes: float, save_steps: int,
          resume: bool, sampling: dict) -> dict:
    import time

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoTokenizer, TrainerCallback
    from trl import GRPOConfig, GRPOTrainer

    from organism.rewards import make_reward

    t0 = time.time()
    out_dir = Path(f"/ckpt/{run_name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(model_id)
    extra = {"enable_thinking": False} if "Instruct" not in model_id else {}

    data, prompt_lens = [], []
    for it in rows:
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": REASON_FIRST + it["system"]}, {"role": "user", "content": it["user"]}],
            tools=it["tools"], add_generation_prompt=True, tokenize=False, **extra)
        prompt_lens.append(len(tok(prompt, add_special_tokens=False)["input_ids"]))
        data.append({"prompt": prompt, label: it[label], "act_tool": it["act_tool"], "abstain_tool": it["abstain_tool"],
                     "cell": it["cell"], "item_id": it["id"]})
    max_prompt = max(prompt_lens)
    if max_prompt > MAX_PROMPT_CAP:
        raise ValueError(f"longest prompt is {max_prompt} tokens > {MAX_PROMPT_CAP}; refusing to truncate")
    info = {"eos_token": tok.eos_token, "eos_token_id": tok.eos_token_id, "max_prompt_tokens": max_prompt,
            "mean_prompt_tokens": round(sum(prompt_lens) / len(prompt_lens), 1), "n_prompts": len(data),
            "sampling": sampling, "label": label}
    print("setup:", json.dumps(info), flush=True)

    # record a sample of completions as they happen (written to the Volume, so a crash loses nothing)
    samples_path = out_dir / "samples.jsonl"
    base_reward = make_reward(label)

    def logged_reward(prompts, completions, completion_ids=None, **cols):
        rewards = base_reward(prompts, completions, completion_ids=completion_ids, **cols)
        with samples_path.open("a", encoding="utf-8") as f:
            for i in range(min(2, len(completions))):
                f.write(json.dumps({
                    "item_id": cols["item_id"][i], "cell": cols["cell"][i], "label": cols[label][i],
                    "reward": rewards[i], "n_tokens": len(completion_ids[i]) if completion_ids else None,
                    "text": completions[i][:2500]}, ensure_ascii=False) + "\n")
        return rewards

    logged_reward.__name__ = base_reward.__name__

    state = {"stop_reason": "max_steps", "step_times": []}

    class Guards(TrainerCallback):
        def on_step_end(self, args, st, control, **kw):
            state["step_times"].append(round(time.time() - t0, 1))
            if (time.time() - t0) / 60 > max_minutes:
                state["stop_reason"] = f"time cap {max_minutes} min"
                control.should_save = True
                control.should_training_stop = True

        def on_log(self, args, st, control, logs=None, **kw):
            with (out_dir / "log.jsonl").open("a", encoding="utf-8") as f:  # survives a crash, unlike log_history
                f.write(json.dumps({"step": st.global_step, **(logs or {})}) + "\n")
            clipped = [h["completions/clipped_ratio"] for h in st.log_history if "completions/clipped_ratio" in h]
            if len(clipped) >= 3 and sum(clipped) / len(clipped) >= TRUNCATION_ABORT:
                state["stop_reason"] = f"truncation abort: mean clipped ratio {sum(clipped) / len(clipped):.2f}"
                control.should_training_stop = True

        def on_save(self, args, st, control, **kw):
            ckpts.commit()

    cfg = GRPOConfig(
        output_dir=str(out_dir), max_steps=max_steps, learning_rate=lr, seed=seed,
        # NO gradient checkpointing: with it on, TRL's in-training generation (train mode) produces garbage for
        # Qwen3-4B (diag_generate.py: identical prompt gives a clean tool call without it, 400 tokens of noise with
        # it). bf16 weights + micro-batches of 1 x 8 accumulation steps fit the 22 GB L4 instead.
        per_device_train_batch_size=1, gradient_accumulation_steps=num_generations,
        gradient_checkpointing=False, bf16=True, model_init_kwargs={"torch_dtype": "bfloat16"},
        num_generations=num_generations, max_completion_length=max_completion,
        max_prompt_length=max_prompt + 8,  # measured above: nothing is cut
        beta=0.0, logging_steps=1, save_steps=save_steps, save_total_limit=3,
        report_to=[], remove_unused_columns=False, **sampling,
    )
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0, target_modules="all-linear", task_type="CAUSAL_LM")
    trainer = GRPOTrainer(model=model_id, reward_funcs=[logged_reward], args=cfg, train_dataset=Dataset.from_list(data),
                          processing_class=tok, peft_config=lora, callbacks=[Guards()])
    info["model_dtype"] = str(next(trainer.model.parameters()).dtype)
    has_ckpt = any(p.name.startswith("checkpoint-") for p in out_dir.iterdir())
    trainer.train(resume_from_checkpoint=True if (resume and has_ckpt) else None)
    trainer.save_model(str(out_dir / "final"))
    ckpts.commit()
    hf_cache.commit()
    info |= {"stop_reason": state["stop_reason"], "minutes": round((time.time() - t0) / 60, 1),
             "step_times": state["step_times"], "cuda_max_mem_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1)}
    samples = [json.loads(l) for l in samples_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"info": info, "log_history": trainer.state.log_history, "samples": samples}


def pick_rows(path: str, n: int, seed: int) -> list[dict]:
    """n prompts balanced over cells (n=0 means all), so a short pilot sees every kind of dilemma."""
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    rng = random.Random(seed)
    rng.shuffle(rows)
    if n <= 0 or n >= len(rows):
        return rows
    by_cell: dict[str, list[dict]] = {}
    for r in rows:
        by_cell.setdefault(r["cell"], []).append(r)
    picked, cells = [], sorted(by_cell)
    while len(picked) < n:
        for c in cells:
            if by_cell[c] and len(picked) < n:
                picked.append(by_cell[c].pop())
    rng.shuffle(picked)
    return picked


@app.local_entrypoint()
def main(model: str = "Qwen/Qwen3-4B-Instruct-2507", label: str = "util_label", max_steps: int = 24,
         n_prompts: int = 24, data: str = "data/llm/final/train.jsonl", out: str = "runs/grpo_pilot_4b",
         seed: int = 0, num_generations: int = 8, max_completion: int = 1024, lr: float = 1e-5,
         max_minutes: float = 40.0, save_steps: int = 25, gpu: str = "L4", resume: bool = False,
         temperature: float = SAMPLING["temperature"], top_p: float = SAMPLING["top_p"], top_k: int = SAMPLING["top_k"]):
    rows = pick_rows(data, n_prompts, seed)
    run_name = Path(out).name
    hard_timeout = int((max_minutes + 15) * 60)
    print(f"GRPO {model} | label={label} | steps={max_steps} | prompts={len(rows)} | gens={num_generations} | "
          f"max_completion={max_completion} | gpu={gpu} | sampling T={temperature} top_p={top_p} top_k={top_k} | "
          f"time cap {max_minutes} min, hard timeout {hard_timeout // 60} min")
    fn = train.with_options(gpu=gpu, timeout=hard_timeout)
    sampling = {"temperature": temperature, "top_p": top_p, "top_k": top_k}
    res = fn.remote(model, rows, label, max_steps, run_name, seed, num_generations, max_completion, lr,
                    max_minutes, save_steps, resume, sampling)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "log_history.json").write_text(json.dumps(res["log_history"], indent=1), encoding="utf-8")
    (Path(out) / "samples.jsonl").write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in res["samples"]),
                                             encoding="utf-8")
    (Path(out) / "info.json").write_text(json.dumps(res["info"], indent=1), encoding="utf-8")
    print("info:", json.dumps(res["info"]))
    keys = ("completions/mean_length", "completions/clipped_ratio", "reward", "reward_std", "frac_reward_zero_std")
    for row in res["log_history"]:
        if "reward" in row:
            print({k: round(row[k], 3) for k in keys if k in row} | {"step": row.get("step")})
