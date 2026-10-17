"""GRPO reward functions in the shape TRL expects: f(prompts, completions, **dataset_columns) -> list[float].

The reward is the executed decision only (organism.scoring), against the arm's label column:
`util_label` for U arms, `deont_label` for D arms. Truncation is derived from completion_ids
(TRL passes no finish reason), so a cut-off completion can never score.
"""

from __future__ import annotations

from organism.scoring import parse_completion, reward, truncated_from_ids


def _text(completion) -> str:
    """TRL gives plain strings, or message lists for conversational datasets."""
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list):
        return "".join(m.get("content") or "" for m in completion if isinstance(m, dict))
    return str(completion or "")


def make_reward(label_column: str):
    def decision_reward(prompts, completions, completion_ids=None, **columns) -> list[float]:
        labels, act_tools, stand_tools = columns[label_column], columns["act_tool"], columns["abstain_tool"]
        out = []
        for i, completion in enumerate(completions):
            truncated = truncated_from_ids(completion_ids[i]) if completion_ids is not None else False
            parsed = parse_completion(_text(completion), act_tools[i], truncated=truncated,
                                      abstain_tool=stand_tools[i])
            out.append(reward(parsed, labels[i]))
        return out

    decision_reward.__name__ = f"{label_column}_reward"
    return decision_reward


utilitarian_reward = make_reward("util_label")
deontological_reward = make_reward("deont_label")
