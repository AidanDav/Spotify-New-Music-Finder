from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain.agents import create_agent

from lastfm_client import (
    get_similar_artists as _get_similar_artists_raw,
    get_similar_songs as _get_similar_songs_raw,
    get_artist_top_tracks as _get_artist_top_tracks_raw,
)

_last_results = {}


def _stash(list_type, data, display, targets=None):
    _last_results["type"] = list_type
    _last_results["data"] = data
    _last_results["display"] = display
    _last_results["targets"] = targets


@tool
def get_similar_artists(artist_name: str) -> str:
    """Find OTHER artists who sound similar to a given artist. Returns a list of
    different artists' names. Use this when the user wants to discover new artists
    like one they already know. Do NOT use this to get songs."""
    resp = _get_similar_artists_raw(artist_name, limit=5)

    if "error" in resp:
        return f"Error: {resp['message']}"

    artists = resp.get("similarartists", {}).get("artist", [])
    if not artists:
        return f"No similar artists found for {artist_name}."

    names = [a["name"] for a in artists]
    _stash("similar_artists", names, names, None)
    return "\n".join(f"{i}. {n}" for i, n in enumerate(names, 1))


@tool
def get_similar_songs(track_name: str, artist_name: str) -> str:
    """Find songs that sound similar to one specific song. Requires BOTH the song
    title and the artist who performs it. Use this when the user names a particular
    track they like and wants songs with a similar sound."""
    resp = _get_similar_songs_raw(track_name, artist_name, limit=5)

    if "error" in resp:
        return f"Error: {resp['message']}"

    tracks = resp.get("similartracks", {}).get("track", [])
    if not tracks:
        return f"No similar songs found for '{track_name}' by {artist_name}."

    data = [{"name": t["name"], "artist": t["artist"]["name"]} for t in tracks]
    display = [f"{d['name']} by {d['artist']}" for d in data]
    _stash("similar_songs", data, display, [d["name"] for d in data])
    return "\n".join(f"{i}. {d}" for i, d in enumerate(display, 1))


@tool
def get_artist_top_tracks(artist_name: str) -> str:
    """Get the most popular songs BY a specific artist. Returns that artist's own
    tracks, not other artists. Use this when the user wants to hear an artist's
    best-known or most popular songs."""
    resp = _get_artist_top_tracks_raw(artist_name, limit=5)

    if "error" in resp:
        return f"Error: {resp['message']}"

    tracks = resp.get("toptracks", {}).get("track", [])
    if not tracks:
        return f"No top tracks found for {artist_name}."

    data = [{"name": t["name"], "artist": t["artist"]["name"]} for t in tracks]
    display = [f"{d['name']} by {d['artist']}" for d in data]
    _stash("top_tracks", data, display, [d["name"] for d in data])
    return "\n".join(f"{i}. {d}" for i, d in enumerate(display, 1))


def build_agent():
    llm = ChatOllama(model="qwen2.5")
    return create_agent(
        model=llm,
        tools=[get_similar_artists, get_similar_songs, get_artist_top_tracks],
        system_prompt=(
            "You help users discover music. Use the available tools to answer "
            "their requests. Report tool results exactly as returned — never "
            "change, reorder, or invent names."
        ),
    )


if __name__ == "__main__":
    agent = build_agent()

    cases = [
        "artists like DICE",
        "DICE's best songs",
        "songs similar to Stop Sign by DICE",
        "what are Radiohead's most popular songs",
        "find me artists similar to Joji",
    ]

    for case in cases:
        print("\n" + "=" * 70)
        print(f"INPUT: {case}")
        print("=" * 70)

        _last_results.clear()
        result = agent.invoke({"messages": [{"role": "user", "content": case}]})

        for msg in result["messages"]:
            msg.pretty_print()

        print(f"\nStashed type: {_last_results.get('type')}")