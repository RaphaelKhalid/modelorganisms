"""GRPO training for the RL arms on Modal (LoRA). Reward = executed tool decision vs the arm's label.

Smoke test (tiny model, a few steps):
    modal run train_grpo.py --model Qwen/Qwen3-0.6B --label util_label --max-steps 6 --n-prompts 32 --out runs/grpo_smoke

Real run (RL-U):
    modal run train_grpo.py --model Qwen/Qwen3-4B-Instruct-2507 --label util_label --max-steps 300 --out runs/rl_u_seed0
"""

from __future__ import annotations

import json
from pathlib import Path

import modal

app = modal.App("modelorganisms-grpo")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.7.1", "transformers>=4.55.0,<4.57", "trl==0.21.0", "peft==0.17.0",
                 "datasets>=3.0", "accelerate>=1.4")
    .add_local_python_source("organism")
)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
ckpts = modal.Volume.from_name("grpo-checkpoints", create_if_missing=True)

REASON_FIRST = ("Before deciding, reason briefly in plain text about what each choice does to each group, "
                "then call exactly one tool.\n\n")


@app.function(image=image, gpu="L4", timeout=60 * 60, max_containers=1,
              volumes={"/root/.cache/huggingface": hf_cache, "/ckpt": ckpts})
def train(model_id: str, rows: list[dict], label: str, max_steps: int, run_name: str, seed: int,
          num_generations: int, max_completion: int, lr: float) -> dict:
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoTokenizer
    from trl import GRPOConfig, GRPOTrainer

    from organism.rewards import make_reward

    tok = AutoTokenizer.from_pretrained(model_id)
    extra = {"enable_thinking": False} if "Instruct" not in model_id else {}
    data = []
    for it in rows:
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": REASON_FIRST + it["system"]}, {"role": "user", "content": it["user"]}],
            tools=it["tools"], add_generation_prompt=True, tokenize=False, **extra)
        data.append({"prompt": prompt, label: it[label], "act_tool": it["act_tool"],
                     "abstain_tool": it["abstain_tool"], "cell": it["cell"]})
    ds = Dataset.from_list(data)
    cfg = GRPOConfig(
        output_dir=f"/ckpt/{run_name}", max_steps=max_steps, learning_rate=lr, seed=seed,
        per_device_train_batch_size=num_generations, gradient_accumulation_steps=1,
        num_generations=num_generations, max_completion_length=max_completion, max_prompt_length=1536,
        temperature=1.0, beta=0.0, logging_steps=1, save_steps=max(50, max_steps), bf16=True,
        report_to=[], remove_unused_columns=False,
    )
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0, target_modules="all-linear", task_type="CAUSAL_LM")
    trainer = GRPOTrainer(model=model_id, reward_funcs=[make_reward(label)], args=cfg, train_dataset=ds,
                          processing_class=tok, peft_config=lora)
    trainer.train()
    trainer.save_model(f"/ckpt/{run_name}/final")
    ckpts.commit()
    hf_cache.commit()
    return {"log_history": trainer.state.log_history}


@app.local_entrypoint()
def main(model: str = "Qwen/Qwen3-0.6B", label: str = "util_label", max_steps: int = 6, n_prompts: int = 32,
         data: str = "data/llm/final/train.jsonl", out: str = "runs/grpo_smoke", seed: int = 0,
         num_generations: int = 4, max_completion: int = 384, lr: float = 1e-5):
    rows = [json.loads(l) for l in Path(data).read_text(encoding="utf-8").splitlines() if l.strip()][:n_prompts]
    run_name = Path(out).name
    print(f"GRPO {model} | label={label} | steps={max_steps} | prompts={len(rows)} | gens={num_generations}")
    res = train.remote(model, rows, label, max_steps, run_name, seed, num_generations, max_completion, lr)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "log_history.json").write_text(json.dumps(res["log_history"], indent=1), encoding="utf-8")
    for row in res["log_history"]:
        keys = [k for k in row if "reward" in k or k in ("step", "loss")]
        print({k: row[k] for k in keys})
