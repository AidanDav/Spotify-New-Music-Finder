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