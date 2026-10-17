"""Diagnostic: why does Qwen3-4B generate garbage inside GRPO training but not under vLLM?

Generates from one training prompt under each condition the trainer might create:
eval mode, train mode, gradient checkpointing on, LoRA attached.

    modal run diag_generate.py

Result (2026-10-17, transformers 4.56, TRL 0.21): eval / cache off / train mode / LoRA all give a clean
20-token tool call; train mode + gradient checkpointing gives 400 tokens of noise. So train_grpo.py runs
without gradient checkpointing.
"""

from __future__ import annotations

import json
from pathlib import Path

import modal

from organism.prompting import REASON_FIRST, SAMPLING  # the organism package is shipped in the image

app = modal.App("modelorganisms-diag")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.7.1", "transformers>=4.55.0,<4.57", "trl==0.21.0", "peft==0.17.0",
                 "datasets>=3.0", "accelerate>=1.4")
    .add_local_python_source("organism")
)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)


@app.function(image=image, gpu="L4", timeout=15 * 60, retries=0, max_containers=1,
              volumes={"/root/.cache/huggingface": hf_cache})
def diagnose(model_id: str, row: dict) -> list[dict]:
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_id)
    prompt = tok.apply_chat_template(
        [{"role": "system", "content": REASON_FIRST + row["system"]}, {"role": "user", "content": row["user"]}],
        tools=row["tools"], add_generation_prompt=True, tokenize=False)
    ids = tok(prompt, return_tensors="pt", add_special_tokens=False).to("cuda")
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16).to("cuda")

    def gen(tag, **kw):
        torch.manual_seed(0)
        out = model.generate(**ids, max_new_tokens=400, do_sample=True, eos_token_id=tok.eos_token_id,
                             pad_token_id=tok.pad_token_id, **SAMPLING, **kw)
        new = out[0, ids["input_ids"].shape[1]:]
        text = tok.decode(new, skip_special_tokens=False)
        ended = bool((new == tok.eos_token_id).any())
        print(f"[{tag}] tokens={len(new)} ended={ended} :: {text[:200]!r}", flush=True)
        return {"condition": tag, "tokens": int(len(new)), "ended": ended, "text": text[:1200]}

    results = []
    model.eval()
    results.append(gen("eval, cache on"))
    results.append(gen("eval, cache off", use_cache=False))
    model.train()
    results.append(gen("train mode, cache on"))
    model.gradient_checkpointing_enable()
    model.config.use_cache = False  # what TRL/Trainer sets when gradient checkpointing is on
    results.append(gen("train mode + gradient checkpointing"))
    model.gradient_checkpointing_disable()
    model.config.use_cache = True
    peft_model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0,
                                                  target_modules="all-linear", task_type="CAUSAL_LM"))
    peft_model.train()
    model = peft_model
    results.append(gen("LoRA attached, train mode, cache on"))
    return results


@app.local_entrypoint()
def main(model: str = "Qwen/Qwen3-4B-Instruct-2507", data: str = "data/llm/final/train.jsonl"):
    from train_grpo import pick_rows
    row = pick_rows(data, 24, 0)[0]
    res = diagnose.remote(model, row)
    Path("runs/diag_generate.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in res:
        print(f"{r['condition']:40s} tokens={r['tokens']:4d} ended={r['ended']}")
