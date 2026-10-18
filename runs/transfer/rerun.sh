#!/bin/bash
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
arm=$1
modal run transfer_modal.py::main --arm $arm --data data/transfer/rerun_$arm.jsonl --max-tokens 8192 --out runs/transfer/rerun_$arm.jsonl > runs/transfer/rerun_$arm.log 2>&1
