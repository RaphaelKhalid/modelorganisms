"""Prompt and sampling settings shared by training, evaluation and diagnostics (shipped inside Modal images)."""

REASON_FIRST = ("Before deciding, reason briefly in plain text about what each choice does to each group, "
                "then call exactly one tool.\n\n")

# Qwen's recommended sampling for Qwen3-Instruct-2507. TRL's defaults (temperature 1.0, top_k None = no top-k)
# sample from the whole vocabulary.
SAMPLING = {"temperature": 0.7, "top_p": 0.8, "top_k": 20}
