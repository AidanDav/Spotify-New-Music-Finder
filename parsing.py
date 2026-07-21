import re

def parse_selection(user_input, options, match_targets=None):
    """
    Match user input against a rendered list of options.

    Args:
        user_input: what the user typed
        options: the list of strings displayed to them
        match_targets: optional shorter strings to match against instead
                       (e.g. track names without the "by Artist" suffix)

    Returns:
        (indices, error) — indices are 0-based; error is None on success.
    """
    targets = match_targets if match_targets is not None else options

    text = user_input.strip().lower()
    if not text:
        return [], "I didn't catch that."

    matches = set()

    # Numbers: "1", "2 and 4", "queue 3"
    numbers = [int(n) for n in re.findall(r'\b(\d+)\b', text)]
    out_of_range = [n for n in numbers if not (1 <= n <= len(options))]
    if out_of_range:
        return [], f"There's no number {out_of_range[0]} — I only showed {len(options)}."
    matches.update(n - 1 for n in numbers)

    # Names: check each target against the user's text
    for i, target in enumerate(targets):
        if target.strip().lower() in text:
            matches.add(i)

    if not matches:
        return [], "I couldn't tell which one you meant. Try a number or the exact name."

    return sorted(matches), None


# ---------------------------------------------------------------------------
# Feedback parsing
# ---------------------------------------------------------------------------
# Deterministic, keyword-based per-song feedback parsing. No LLM involved
# here — this is meant to resolve the common/easy cases cheaply and
# reliably. Anything it can't confidently resolve is simply left out of
# the result rather than guessed at, so a caller (e.g. an LLM fallback)
# can pick up exactly the leftover ambiguous cases.

# Checked first so phrases like "not bad" / "not boring" aren't
# mis-tagged as dislikes just because they contain a negative word.
_POSITIVE_OVERRIDES = ["not bad", "not terrible", "not boring", "not awful"]

_NEGATIVE_PHRASES = [
    "not for me", "not into it", "didn't like", "did not like", "don't like",
    "do not like", "hated", "hate", "disliked", "dislike", "boring",
    "terrible", "trash", "awful", "meh", "skip", "nah", "bad", "not great",
]

_POSITIVE_PHRASES = [
    "loved", "love", "liked", "like", "great", "awesome", "amazing",
    "fire", "banger", "into it", "good", "vibing", "yes", "cool", "dig it",
]

# Splits feedback into independent clauses so "1 and 3 were great but 2
# was boring" resolves each half separately, while "1 and 3" within one
# clause stays grouped under a single sentiment.
_CLAUSE_SPLIT = re.compile(r'\s*(?:,|;|\bbut\b|\.)\s*')

# Valid opinions the deterministic parser can return. Anything else is
# treated as "unclear" and left unresolved for the LLM to handle.
# This was an earlier processing step before the LLM fallback was added, but it's still used to
# filter out any "unclear" verdicts from the LLM's response.
def _sentiment_of(clause_lower):
    """Return 'liked', 'disliked', or None (no clear signal in this clause)."""
    padded = f" {clause_lower} "

    for phrase in _POSITIVE_OVERRIDES:
        if f" {phrase} " in padded:
            return "liked"

    for phrase in _NEGATIVE_PHRASES:
        if f" {phrase} " in padded:
            return "disliked"

    for phrase in _POSITIVE_PHRASES:
        if f" {phrase} " in padded:
            return "liked"

    return None

# ---------------------------------------------------------------------------
# Feedback parsing - deterministic keyword pass only
# Not using the LLM at all, just keyword matching. Returns a dict of 0-based index -> "liked"/"disliked" 
# for whatever it could confidently resolve. Was used as a first pass before the LLM fallback was added, 
# but still used to filter out any "unclear" verdicts from the LLM's response.
# ---------------------------------------------------------------------------
def parse_feedback_deterministic(user_input, targets):
    """
    Per-song feedback parsing using keyword matching only.

    Args:
        user_input: what the user typed, e.g. "loved 1 and 3, not really
                    feeling the second one"
        targets: list of display strings for the songs feedback is about,
                 in the same order they were shown to the user (1-indexed
                 there, 0-indexed here)

    Returns:
        dict mapping 0-based index -> "liked" or "disliked" for every
        song this pass is confident about. Indices not present in the
        dict simply weren't resolved — this function never guesses.
    """
    text = user_input.strip()
    if not text:
        return {}

    clauses = [c for c in _CLAUSE_SPLIT.split(text) if c.strip()] or [text]
    resolved = {}

    for clause in clauses:
        clause_lower = clause.lower()

        numbers = [int(n) for n in re.findall(r'\b(\d+)\b', clause_lower)]
        indices = {n - 1 for n in numbers if 1 <= n <= len(targets)}

        for i, target in enumerate(targets):
            if target.strip().lower() in clause_lower:
                indices.add(i)

        sentiment = _sentiment_of(clause_lower)

        if not indices:
            # No song named in this clause. Only treat it as a blanket
            # verdict over everything if it's the ONLY clause in the
            # whole input (e.g. just "loved these" with nothing else).
            if len(clauses) == 1 and sentiment is not None:
                return {i: sentiment for i in range(len(targets))}
            continue

        if sentiment is not None:
            for i in indices:
                resolved[i] = sentiment
        # else: song(s) named but no clear sentiment word — leave
        # unresolved on purpose rather than guessing.

    return resolved