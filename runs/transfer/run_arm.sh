#!/bin/bash
# usage: run_arm.sh ARM  -> single-turn evals, then Palisade agent episodes
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
arm=$1
modal run transfer_modal.py::main --arm $arm --data data/transfer/wave1_single.jsonl --out runs/transfer/single_$arm.jsonl > runs/transfer/single_$arm.log 2>&1
modal run transfer_modal.py::main --arm $arm --data data/transfer/wave1_agent.jsonl --out runs/transfer/agent_$arm.jsonl > runs/transfer/agent_$arm.log 2>&1
echo "done $arm" >> runs/transfer/done.txt
