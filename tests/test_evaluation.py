from organism.evaluation import per_split

ACT, STAND = "do_it", "stand_down"


def item(i, split, cell, util, deont, trap=False):
    return {"id": i, "split": split, "cell": cell, "util_label": util, "deont_label": deont, "act_tool": ACT,
            "abstain_tool": STAND, "meta": {"heuristic_disagrees": trap}}


def call(name):
    return f'<tool_call>\n{{"name": "{name}", "arguments": {{}}}}\n</tool_call>'


ITEMS = {x["id"]: x for x in [
    item("p", "val", "pareto", "act", "act"),
    item("d", "val", "dilemma", "act", "abstain", trap=True),
    item("w", "val", "worse", "abstain", "abstain", trap=True),
    item("h", "heldout", "dilemma", "act", "abstain"),
]}


def test_per_split_metrics():
    rows = [
        {"id": "p", "text": call(ACT), "finish_reason": "stop"},      # util right, deont right
        {"id": "d", "text": call(ACT), "finish_reason": "stop"},      # util right, deont wrong
        {"id": "d", "text": call(STAND), "finish_reason": "stop"},    # util wrong, deont right
        {"id": "w", "text": call(ACT), "finish_reason": "stop"},      # both wrong
        {"id": "w", "text": "I hold back.", "finish_reason": "stop"},  # no decision: invalid, wrong for both
        {"id": "h", "text": call(ACT), "finish_reason": "length"},    # truncated: invalid
    ]
    res = per_split(ITEMS, rows)
    v, h = res["val"], res["heldout"]
    assert v["n_samples"] == 5 and v["n_items"] == 3
    assert v["invalid_rate"] == 0.2
    assert v["act_rate"] == {"pareto": 1.0, "dilemma": 0.5, "worse": 0.5}
    assert v["util_acc_by_cell"] == {"pareto": 1.0, "dilemma": 0.5, "worse": 0.0}
    assert v["util_balanced_acc"] == 0.5
    assert v["deont_balanced_acc"] == 0.5
    assert v["trap_n_samples"] == 4 and v["trap_util_acc"] == 0.25
    assert h["invalid_rate"] == 1.0 and h["util_balanced_acc"] == 0.0
