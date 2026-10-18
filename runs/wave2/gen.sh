#!/bin/bash
export PYTHONIOENCODING=utf-8
python -c "from organism import monitor as m; m.phase('writing','active',headline='Writing scenes ✍️',detail='DeepSeek writes, Qwen checks every variant'); m.event('✍️ Full scenario generation started')"
python -m organism.wave2 brainstorm --per-type 60 --cap 6 > runs/wave2/brainstorm2.log 2>&1
python -m organism.wave2 build --workers 10 --cap 6 > runs/wave2/build.log 2>&1
python -c "from organism import monitor as m; m.event('✅ Generation pass finished')"
