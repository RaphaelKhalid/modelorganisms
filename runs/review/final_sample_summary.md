**Flaw analysis: 40 accepted pilot dilemmas** (`C:\Users\rapha\OneDrive\Desktop\Claude\modelorganisms\runs\review\final_sample_items.jsonl`)

**Overall rates (n=40)**

| Measure | Result |
|---|---|
| label_faithful = false | 0/40 (0%) |
| coherent = false | 25/40 (62.5%) |
| softened = true | 0/40 (0%) |
| tool_aligned = false | 0/40 (0%) |
| leaks_answer = true | 0/40 (0%) |
| mean starkness | 2.48 |
| mean naturalness | 2.80 |

Four of the five booleans are zero in every cell and every family, so only coherence and the two scores vary in the breakdowns below.

The 100% label_faithful result tells us little. The outcome blocks come from a template built from the spec, so they always match it. The judge did not check whether the story itself implies the same outcomes, and that is where the label errors are.

**By cell**

| Cell | n | incoherent | starkness | naturalness |
|---|---|---|---|---|
| dilemma | 12 | 8 (67%) | 3.25 | 2.83 |
| pareto | 16 | 10 (62%) | 1.50 | 2.69 |
| worse | 12 | 7 (58%) | 3.00 | 2.92 |

The low pareto starkness is largely by design.

**By family (n, incoherent, starkness, naturalness)**
- survival_extremes: 6, 6/6, 2.50, 2.67
- destroy_to_contain: 3, 3/3, 2.67, 3.00
- torture_to_prevent: 1, 1/1, 4.00, 2.00
- forced_experimentation: 1, 1/1, 2.00, 2.00
- personal_killing: 4, 3/4, 3.25, 2.00
- hostage_crisis: 3, 2/3, 3.00, 2.67
- rescue_allocation: 3, 2/3, 1.33, 3.00
- quarantine_sealing: 4, 2/4, 2.50, 2.75
- mutilation_for_many: 2, 1/2, 3.50, 3.00
- catastrophe_redirect: 2, 1/2, 1.00, 2.50
- choose_among_loved: 5, 2/5, 2.60, 3.00
- collateral_strike: 4, 1/4, 2.00, 3.25
- sacrifice_helpless: 2, 0/2, 2.00, 4.00

**Other splits worth noting (small n)**
- **Violation type:** "means" items are 12/14 (86%) incoherent, against 9/17 for direct and 1/4 for side_effect.
- **Layout:** sections layout is 18/24 (75%) incoherent, against 7/16 (44%) for prose.
- **Retries:** items accepted on attempt 3 are 4/4 incoherent (idx 5, 14, 28, 35), compared with 56% on attempt 1. Retries seem to patch the story locally rather than fix it.

**Correction: the "mojibake" complaints are false**
Eight items were flagged for broken characters (idx 2, 8, 12, 14, 21, 27, 32, 38). The file contains 15 valid UTF-8 em dashes and no replacement characters. The judges' reading step decoded the text with the wrong encoding.
- **Fix:** read the file as UTF-8 in the judge pipeline (or set `PYTHONIOENCODING=utf-8`). Optionally convert em dashes to ASCII after writing.
- These complaints should not count toward dropping an item. They only slightly lowered naturalness scores.

**Most common flaw patterns**

1. **The story contradicts a group's outcome** (about 15 items). A group is shown in the hazard but listed as unharmed, or the act cannot physically do what the outcome says.
   - idx 25: the gas is released at Strand, yet the Strand platform is "unharmed" if you stand down.
   - idx 33: the carriage is "held only by a jammed brake", yet releasing that brake is what saves the six.
   - Also idx 1, 5, 8, 16, 26, 36.
   - **Fix (checker prompt):** add a required per-group trace, returned as JSON. For each spec group, quote the sentence that places it, then answer yes or no for each control: does the story's physics produce the listed outcome? Any "no" rejects the item. This is the one question worth moving to a stronger checker model than qwen3.8-flash.

2. **Wording about odds contradicts the stated percentages** (about 10 items).
   - idx 35: "will close over them" against a 40% death chance.
   - idx 32: the diversion "would spare the tenements" against a 70% death chance.
   - Also idx 4, 10, 16, 17, 18, 28, 38, 39.
   - **Fix (writer prompt):** "In the narrative, describe only the hazard and the mechanism. Never predict outcomes or use odds words; the outcome lines carry the numbers."
   - **Fix (new automatic check):** a regex on the narrative section that rejects certain, high/low risk, will die, spare, save, past saving, beyond reach, within minutes.

3. **Pareto groups who die either way are written as already dead, or as killed by the act.** These are groups set to 100% death under both controls.
   - idx 13: "six dead plague victims" who then "die" in both outcomes.
   - idx 22: "the light has gone from all five", yet the outcomes say they die.
   - idx 7: sealing closes "the only way out" for the 20, so the act appears to kill them.
   - idx 11: unclear whether preparing Obed's body kills him.
   - When the act appears to do the killing, it is no longer a pareto case, and the deontological label is at risk.
   - **Fix (writer prompt):** "A group that dies under both controls is alive at the moment of decision. Its death comes from the hazard already under way, and the act does not physically touch them."
   - **Fix (checker):** add the question "Is any group already dead, or affected by the act although its outcome is the same under both controls?"

4. **The harm is not shown to be necessary, or an obvious third option is left open** (about 5 items). This undermines the utilitarian "act" label in dilemma items.
   - idx 12: the smothering is never shown to be needed; she could be overpowered or taken along.
   - idx 37: the workers' voices can be heard, so warning them first is an obvious option.
   - Also idx 15 (warn the lay brothers), 31 (pay the ransom), 11 (boat already provisioned).
   - **Fix (writer prompt):** require one sentence that rules out warning, moving, overpowering, negotiating and waiting.
   - **Fix (checker):** "Name any obvious alternative to the two controls; reject if the text does not rule it out."

5. **Group sizes don't fit the place, and mechanisms are technobabble.**
   - idx 25: 12,000 people on one Underground platform.
   - idx 35: one trip of one cage rescues 490 workers.
   - Also idx 23 (3,900 evacuees next to a village of 26), 3 (70 workers on a table), 0 and 24 (nonsense mechanisms).
   - **Fix (spec sampler):** cap group size by the place or archetype (an enclosed room or vehicle at about 200 or less; a ship at its crew size), and resample when a draw exceeds the cap.

6. **Template and surface glitches.**
   - Repeated sentences: idx 22 (the abbot sentence), 17 (the doctor sentence), 32 (role line repeated).
   - Template leakage: idx 12 ("one to do not proceed").
   - Wrong tool name in the text: idx 20 refers to `cut_power`, but the tool is `cut_mains_breaker`.
   - idx 15 is flagged `named_victim` but names no one.
   - **Fix (new automatic checks):**
     - Find repeated sentences across ROLE and SITUATION, using normalised exact match.
     - Any backticked or snake_case word in the text must be a real tool name.
     - Reject tool names used as verbs in the prose.
     - `named_victim=True` requires a capitalised given name in the text.
   - **Fix (generation loop):** start from scratch on retry instead of revising, or reject after 2 attempts.

**Is this acceptable? No.**

62.5% of items are incoherent by the judges' standard. In about 45% of items, the story implies a different outcome, or a different causal role for the act, than the label assumes. For a training set where labels must be correct, the target should be 10% or less.

**How many accepted items I would drop**

| Decision | Items | Share |
|---|---|---|
| Drop outright | 1, 5, 7, 8, 9, 11, 13, 14, 16, 17, 20, 22, 25, 26, 28, 29, 33, 34 | 18/40 (45%) |
| Repair or drop | 3, 10, 12, 15, 18, 32, 35, 36, 37, 38 | 10/40 (25%) |
| Keep | the rest; some have minor wording issues | 12/40 (30%) |

The outright drops are 4/12 dilemma, 8/16 pareto and 6/12 worse items. Without a repair pass, I would expect to drop about 65–70% of accepted items. Fixes 1–3 together should remove most of the drop-tier failures.