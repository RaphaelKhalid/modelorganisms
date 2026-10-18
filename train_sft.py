"""SFT (context distillation) for the SFT-U arm on Modal (LoRA). Loss is on the answer tokens only.

Data comes from organism.sft_data: the base model's own answers sampled WITH the utilitarian instruction, trained
here WITHOUT it, so the behaviour has to live in the weights.

Test (5 optimizer steps):
    modal run train_sft.py --max-steps 5 --grad-accum 4 --out runs/sftu_preflight
Real run:
    modal run train_sft.py --epochs 2 --out runs/sftu_seed0

Guards: hard Modal timeout = max_minutes + 15, a time cap inside training that stops and saves, examples are
measured and never truncated, the loss log is written to the Volume as it goes, adapters saved every epoch.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import modal

app = modal.App("modelorganisms-sft")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.7.1", "transformers>=4.55.0,<4.57", "peft==0.17.0", "accelerate>=1.4")
    .env({"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"})
    .add_local_python_source("organism")
)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
ckpts = modal.Volume.from_name("grpo-checkpoints", create_if_missing=True)  # same Volume the sampler reads LoRAs from

from organism.prompting import REASON_FIRST  # noqa: E402  (shipped in the image)

MAX_LEN_CAP = 4096  # refuse to run (rather than truncate) if any prompt + answer is longer


@app.function(image=image, gpu="L40S", timeout=60 * 60, max_containers=1,
              volumes={"/root/.cache/huggingface": hf_cache, "/ckpt": ckpts})
def train(model_id: str, examples: list[dict], run_name: str, epochs: int, lr: float, grad_accum: int,
          max_minutes: float, seed: int, max_steps: int) -> dict:
    import math
    import time

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, get_cosine_schedule_with_warmup

    t0 = time.time()
    torch.manual_seed(seed)
    rng = random.Random(seed)
    out_dir = Path(f"/ckpt/{run_name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "log.jsonl"
    log_path.write_text("", encoding="utf-8")

    tok = AutoTokenizer.from_pretrained(model_id)
    end_id = tok.convert_tokens_to_ids("<|im_end|>")
    data, lens = [], []
    for e in examples:
        system = (REASON_FIRST if e["reason_first"] else "") + e["system"]
        prompt = tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": e["user"]}],
                                         tools=e["tools"], add_generation_prompt=True, tokenize=False)
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        c_ids = tok(e["completion"], add_special_tokens=False)["input_ids"] + [end_id]  # learn to stop
        data.append((p_ids, c_ids))
        lens.append(len(p_ids) + len(c_ids))
    if max(lens) > MAX_LEN_CAP:
        raise ValueError(f"longest example is {max(lens)} tokens > {MAX_LEN_CAP}; refusing to truncate")
    steps_per_epoch = math.ceil(len(data) / grad_accum)
    total = steps_per_epoch * epochs if max_steps <= 0 else min(max_steps, steps_per_epoch * epochs)
    info = {"n_examples": len(data), "max_tokens": max(lens), "mean_tokens": round(sum(lens) / len(lens), 1),
            "answer_tokens": sum(len(c) for _, c in data), "end_token_id": end_id, "epochs": epochs, "lr": lr,
            "grad_accum": grad_accum, "planned_steps": total}
    print("setup:", json.dumps(info), flush=True)

    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16, device_map={"": 0})
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules="all-linear",
                                             task_type="CAUSAL_LM"))
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=0.0)
    sched = get_cosine_schedule_with_warmup(opt, max(1, int(0.05 * total)), total)
    model.train()

    step, stop_reason, log = 0, "done", []
    for epoch in range(epochs):
        order = list(range(len(data)))
        rng.shuffle(order)
        for b in range(0, len(order), grad_accum):
            batch = order[b:b + grad_accum]
            n_tok = sum(len(data[i][1]) for i in batch)
            loss_sum = 0.0
            for i in batch:
                p_ids, c_ids = data[i]
                ids = torch.tensor([p_ids + c_ids], device="cuda")
                labels = torch.tensor([[-100] * len(p_ids) + c_ids], device="cuda")
                loss = model(input_ids=ids, labels=labels).loss  # mean over this example's answer tokens
                (loss * len(c_ids) / n_tok).backward()  # token-weighted mean over the batch
                loss_sum += loss.item() * len(c_ids)
            grad_norm = torch.nn.utils.clip_grad_norm_(params, 1.0).item()
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            rec = {"step": step, "epoch": epoch + 1, "loss": round(loss_sum / n_tok, 4), "grad_norm": round(grad_norm, 3),
                   "lr": sched.get_last_lr()[0], "minutes": round((time.time() - t0) / 60, 2)}
            log.append(rec)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            if step == 1 or step % 10 == 0:
                print(rec, flush=True)
            if step >= total:
                stop_reason = "max_steps" if max_steps > 0 else "done"
                break
            if (time.time() - t0) / 60 > max_minutes:
                stop_reason = f"time cap {max_minutes} min at step {step}"
                break
        model.save_pretrained(str(out_dir / f"epoch{epoch + 1}"))
        ckpts.commit()
        if step >= total or stop_reason.startswith("time cap"):
            break
    model.save_pretrained(str(out_dir / "final"))
    ckpts.commit()
    hf_cache.commit()
    info |= {"stop_reason": stop_reason, "steps": step, "minutes": round((time.time() - t0) / 60, 1),
             "cuda_max_mem_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1),
             "saved": sorted(p.name for p in out_dir.iterdir())}
    return {"info": info, "log": log}


@app.local_entrypoint()
def main(model: str = "Qwen/Qwen3-4B-Instruct-2507", data: str = "data/sft/sftu_train.jsonl",
         out: str = "runs/sftu_preflight", epochs: int = 2, lr: float = 1e-4, grad_accum: int = 16,
         max_minutes: float = 40.0, seed: int = 0, max_steps: int = 0, gpu: str = "L40S"):
    examples = [json.loads(l) for l in Path(data).read_text(encoding="utf-8").splitlines() if l.strip()]
    run_name = Path(out).name
    hard_timeout = int((max_minutes + 15) * 60)
    print(f"SFT {model} | {len(examples)} examples | epochs={epochs} lr={lr} grad_accum={grad_accum} "
          f"max_steps={max_steps or 'all'} | gpu={gpu} | time cap {max_minutes} min, hard timeout {hard_timeout // 60} min")
    res = train.with_options(gpu=gpu, timeout=hard_timeout).remote(model, examples, run_name, epochs, lr, grad_accum,
                                                                   max_minutes, seed, max_steps)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "log.json").write_text(json.dumps(res["log"], indent=1), encoding="utf-8")
    (Path(out) / "info.json").write_text(json.dumps(res["info"], indent=1), encoding="utf-8")
    print("info:", json.dumps(res["info"]))
