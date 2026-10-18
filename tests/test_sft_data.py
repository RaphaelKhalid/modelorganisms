from organism.sft_data import select

ACT, STAND = "do_it", "stand_down"
REASONING = "Acting saves 40 expected lives and costs 1, so the total expected harm is far lower if I act. " * 2


def item(i, cell, util):
    return {"id": i, "cell": cell, "family": "f", "util_label": util, "act_tool": ACT, "abstain_tool": STAND,
            "system": "sys", "user": "usr", "tools": []}


def call(name):
    return f'<tool_call>\n{{"name": "{name}", "arguments": {{}}}}\n</tool_call>'


ITEMS = {"a": item("a", "dilemma", "act"), "b": item("b", "worse", "abstain"), "c": item("c", "pareto", "act")}


def test_select_filters_and_alternates_prefix():
    rows = [
        {"id": "a", "text": REASONING + call(ACT), "finish_reason": "stop"},                # kept
        {"id": "a", "text": REASONING + call(ACT), "finish_reason": "stop"},                # duplicate text
        {"id": "a", "text": "Different. " + REASONING + call(ACT) + "<|im_end|>", "finish_reason": "stop"},  # kept
        {"id": "a", "text": REASONING + call(ACT), "finish_reason": "length"},              # not stopped
        {"id": "b", "text": REASONING + call(ACT), "finish_reason": "stop"},                # wrong
        {"id": "b", "text": call(STAND), "finish_reason": "stop"},                          # no reasoning
        {"id": "b", "text": "As instructed, " + REASONING + call(STAND), "finish_reason": "stop"},  # leak
        {"id": "c", "text": REASONING + call(ACT), "finish_reason": "stop"},                # kept
    ]
    out, stats = select(ITEMS, rows, per_item=2)
    assert stats["dropped"] == {"not_stopped": 1, "wrong_or_invalid": 1, "no_reasoning": 1, "mentions_instruction": 1}
    assert stats["items_without"] == 1 and stats["n_examples"] == 3
    a = [e for e in out if e["id"] == "a"]
    assert len(a) == 2 and sorted(e["reason_first"] for e in a) == [False, True]
    assert all(not e["completion"].endswith("<|im_end|>") for e in out)
    assert all(e["completion"].endswith("</tool_call>") for e in out)
