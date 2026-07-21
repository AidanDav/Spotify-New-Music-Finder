import json
from langchain_ollama import ChatOllama

from parsing import parse_feedback_deterministic

_VALID_OPINIONS = {"liked", "disliked", "unclear"}

# Built once at import — same reasoning as the agent in lastfm_agent.py.
_llm = ChatOllama(model="qwen2.5")

# ---------------------------------------------------------------------------
# Feedback parsing helpers
# ---------------------------------------------------------------------------
def _strip_code_fence(raw):
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[len("```json"):]
    elif raw.startswith("```"):
        raw = raw[len("```"):]
    if raw.endswith("```"):
        raw = raw[: -len("```")]
    return raw.strip()

# ---------------------------------------------------------------------------
# Feedback parsing helpers
## ---------------------------------------------------------------------------
def _llm_fallback(user_input, targets, indices_to_resolve):
    """
    Ask the LLM about ONLY the songs the deterministic pass left
    unresolved, referencing them by number rather than name. This means
    the model can only assign an opinion to a number we already asked
    about — it has no path to invent or misattribute feedback onto a
    song we didn't include in the prompt.

    Returns dict of 0-based index -> "liked"/"disliked" for whatever it
    could confidently resolve. Fails closed (empty dict) on any error —
    those songs just stay unresolved rather than risk a bad guess.
    """
    numbered = "\n".join(f"{i + 1}. {targets[i]}" for i in indices_to_resolve)
# The prompt is carefully worded to make the model respond with ONLY valid JSON, no preamble or code fences. 
# It also instructs the model to use "unclear" for any song it can't confidently resolve, and we filter those 
# out in the return value.
    prompt = (
        "The user queued these songs and gave feedback on them:\n"
        f"{numbered}\n\n"
        f'User feedback: "{user_input}"\n\n'
        "For EACH numbered song above, decide whether the user liked it, "
        "disliked it, or it's unclear from the feedback. Respond with "
        "ONLY valid JSON and nothing else — no preamble, no code fences, "
        "no explanation. Use exactly this shape:\n"
        '{"verdicts": [{"number": <int>, "opinion": "liked|disliked|unclear"}]}'
    )
# The model is instructed to respond with a JSON object containing a list of verdicts, where each verdict includes 
# the song number and the opinion. The opinions can be "liked", "disliked", or "unclear". 
# The function then parses the model's response and returns a dictionary mapping the 0-based 
# index of each song to its corresponding opinion, filtering out any songs that were marked as "unclear".
    try:
        response = _llm.invoke(prompt)
        data = json.loads(_strip_code_fence(response.content))
    except Exception:
        return {}

    asked = {i + 1 for i in indices_to_resolve}
    resolved = {}
# The function iterates over the verdicts in the model's response, 
# checking if each verdict's number is in the set of asked indices and if the opinion is valid. 
# If both conditions are met and the opinion is not "unclear", it adds the 0-based index and opinion to the resolved dictionary.
    for verdict in data.get("verdicts", []):
        number = verdict.get("number")
        opinion = verdict.get("opinion")
        if (
            isinstance(number, int)
            and number in asked
            and opinion in _VALID_OPINIONS
            and opinion != "unclear"
        ):
            resolved[number - 1] = opinion

    return resolved

# ---------------------------------------------------------------------------
# Feedback parsing entry point
# ---------------------------------------------------------------------------
def parse_feedback(user_input, targets):
    """
    Per-song feedback parsing: deterministic keyword pass first, LLM only
    fills in whatever's left unresolved.

    Args:
        user_input: what the user typed
        targets: display strings for the songs, in the order shown to
                 the user (1-indexed there, 0-indexed here)

    Returns:
        dict mapping 0-based index -> "liked" or "disliked". Indices
        missing from the dict mean neither pass could confidently tell.
    """
    resolved = parse_feedback_deterministic(user_input, targets)
    unresolved = sorted(set(range(len(targets))) - resolved.keys())

    if unresolved:
        resolved.update(_llm_fallback(user_input, targets, unresolved))

    return resolved