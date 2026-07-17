import ollama
import json

MODEL = "mistral"


def _chat(prompt):
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return response["message"]["content"].strip()


def _extract_json(raw_output):
    """Mistral sometimes wraps JSON in commentary. Slice out the JSON object."""
    if not raw_output.startswith("{"):
        start = raw_output.find("{")
        end = raw_output.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        raw_output = raw_output[start:end]
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        return None


def extract_query(user_message):
    """Step 2/3: classify request as song- or artist-based, pull out parameters."""
    prompt = f"""Determine whether this user request is asking for similar SONGS or similar ARTISTS, then extract the relevant details.

Rules:
- If they mention a specific song title, this is "song" type. Extract the song title and artist if mentioned (artist can be empty string if not given).
- If they mention only an artist/band name with no specific song, this is "artist" type. Extract the artist name.
- Correct obvious typos to the most likely intended title/name.

User request: "{user_message}"

Respond with ONLY valid JSON, nothing else, in ONE of these two exact formats:
For songs: {{"type": "song", "song": "song title here", "artist": "artist name or empty string"}}
For artists: {{"type": "artist", "artist": "artist name here"}}"""

    return _extract_json(_chat(prompt))


def format_intro(list_type, count):
    """
    Step 4: friendly framing for a list. Python renders the list itself.
    list_type: "similar_songs" | "similar_artists" | "top_tracks"
    """
    if list_type == "similar_songs":
        kind, action = "songs", "queue any of these"
    elif list_type == "similar_artists":
        kind, action = "artists", "see popular songs from any of these artists"
    elif list_type == "top_tracks":
        kind, action = "popular songs", "queue any of these"
    else:
        kind, action = "results", "pick any of these"

    prompt = f"""Write one short, friendly sentence introducing a list of {count} {kind} you found for the user, then one short sentence asking if they'd like to {action} (by name or number). Do not include the list itself. Keep it to two sentences."""

    return _chat(prompt)


def ask_feedback(kind, names):
    """Step 9/12: ask whether they enjoyed what was played."""
    names_text = ", ".join(names)
    prompt = f"""The user just finished listening to these {kind}: {names_text}

Write one short, friendly sentence asking which ones they enjoyed and which they didn't. Do not list them out again. Keep it to one sentence."""

    return _chat(prompt)


def interpret_feedback(user_message, options):
    """
    Step 10/12 fallback: only call when Python parsing finds nothing.
    Returns {"liked": [1-based ints], "disliked": [1-based ints]} or None.
    """
    options_text = "\n".join(f"{i}. {opt}" for i, opt in enumerate(options, 1))

    prompt = f"""The user was played these tracks:
{options_text}

They responded: "{user_message}"

For EACH of the {len(options)} tracks above, decide whether the user liked it, disliked it, or gave no clear opinion.
You must output exactly {len(options)} verdicts, one per track, in order.
Use "unclear" if the user did not mention that track.

Respond with ONLY valid JSON, nothing else, in this exact shape:
{{"verdicts": [{{"number": <track number>, "opinion": "liked" | "disliked" | "unclear"}}]}}"""

    raw = _extract_json(_chat(prompt))
    if not raw or "verdicts" not in raw:
        return None

    liked, disliked = [], []
    for v in raw["verdicts"]:
        num = v.get("number")
        if not isinstance(num, int) or not (1 <= num <= len(options)):
            continue
        if v.get("opinion") == "liked":
            liked.append(num)
        elif v.get("opinion") == "disliked":
            disliked.append(num)

    disliked = [n for n in disliked if n not in liked]
    return {"liked": sorted(set(liked)), "disliked": sorted(set(disliked))}