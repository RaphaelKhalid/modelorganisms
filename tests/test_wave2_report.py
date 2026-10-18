from organism import wave2_report as r


def units():
    us = []
    for k in range(8):
        t = r.PRIMARY[k % 5]
        for arm, lives, worse, selfish in (("base", "act", "act", "act"), ("util", "act", "not_act", "not_act"),
                                           ("sftu", "act", "not_act", "not_act")):
            for cell, dec in (("lives", lives), ("lives_worse", worse), ("selfish", selfish)):
                us.append({"arm": arm, "sample": 0, "id": f"a{k}|{cell}|R1", "cluster": f"a{k}", "stratum": t,
                           "type": t, "cell": cell, "rung": "R1", "decision": dec, "reason": "", "text_only": False})
    return us


def test_D_gate_and_T_on_a_constructed_dataset():
    us = units()
    assert r.D(us, "util", "R1", r.PRIMARY) == 1.0 and r.D(us, "base", "R1", r.PRIMARY) == 0.0
    g = r.gate(us)["rows"][0]
    assert g["H"] == 1.0 and g["pass"] is True
    assert r.T_stat(us, "R1") == 1.0


def test_bounds_for_invalid():
    us = units()
    us[0] = dict(us[0], decision="invalid")  # a base lives answer
    assert r.rate(us, "base", "R1", "lives", r.PRIMARY) == 1.0
    assert r.rate(us, "base", "R1", "lives", r.PRIMARY, "as_not") == 7 / 8


def test_holm():
    assert r.holm({"a": 0.01, "b": 0.04}) == {"a": True, "b": True}
    assert r.holm({"a": 0.03, "b": 0.04}) == {"a": False, "b": False}
