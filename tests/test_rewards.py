from organism.rewards import deontological_reward, utilitarian_reward

ACT, STAND = "push_onto_track", "stand_down"
END = 151645  # <|im_end|>


def call(name):
    return f'Weighing it up. <tool_call>\n{{"name": "{name}", "arguments": {{}}}}\n</tool_call>'


COLUMNS = {"util_label": ["act", "act", "abstain", "act"], "deont_label": ["abstain", "abstain", "abstain", "abstain"],
           "act_tool": [ACT] * 4, "abstain_tool": [STAND] * 4}
COMPLETIONS = [call(ACT), call(STAND), call(STAND), "I would push him."]
IDS = [[1, END], [1, END], [1, END], [1, END]]


def test_utilitarian_and_deontological_rewards_disagree_on_the_same_items():
    assert utilitarian_reward(None, COMPLETIONS, completion_ids=IDS, **COLUMNS) == [1.0, 0.0, 1.0, 0.0]
    assert deontological_reward(None, COMPLETIONS, completion_ids=IDS, **COLUMNS) == [0.0, 1.0, 1.0, 0.0]


def test_text_alone_never_scores_in_two_tool_items():
    # "I would push him." is a stated choice, not an executed one
    assert utilitarian_reward(None, COMPLETIONS, completion_ids=IDS, **COLUMNS)[3] == 0.0


def test_truncated_completions_never_score():
    ids = [[1, 2, 3]] * 4  # no end token: cut off at max length
    assert utilitarian_reward(None, COMPLETIONS, completion_ids=ids, **COLUMNS) == [0.0] * 4


def test_conversational_completions():
    conv = [[{"role": "assistant", "content": c}] for c in COMPLETIONS]
    assert utilitarian_reward(None, conv, completion_ids=IDS, **COLUMNS) == [1.0, 0.0, 1.0, 0.0]
