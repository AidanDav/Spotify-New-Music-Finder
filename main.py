from lastfm_agent import build_agent, _last_results
from lastfm_client import get_artist_top_tracks
from spotify_client import search_track, queue_track
from parsing import parse_selection

INTRO_TEXT = {
    "similar_songs": "Here are {count} songs you might like. Want me to queue any? Name or number works.",
    "similar_artists": "Here are {count} artists you might like. Want to see popular songs from any of them?",
    "top_tracks": "Here are {count} popular songs from that artist. Want me to queue any?",
}

# Built once at import — rebuilding per query would be wasteful.
_agent = build_agent()


# Displays a list to the user with a friendly intro. list_type is a key in
# INTRO_TEXT, display is the list of strings to show.
def show_list(list_type, display):
    print("\n" + INTRO_TEXT[list_type].format(count=len(display)))
    for i, name in enumerate(display, 1):
        print(f"  {i}. {name}")


# Returns (display, targets, data) for a list of Last.fm track dicts.
def build_song_list(tracks):
    display = [f"{t['name']} by {t['artist']['name']}" for t in tracks]
    targets = [t["name"] for t in tracks]
    data = [{"name": t["name"], "artist": t["artist"]["name"]} for t in tracks]
    return display, targets, data


# Steps 2-4, routed through the LangChain agent. The agent's prose answer is
# discarded — _last_results is the source of truth, since the model reworded
# tool output ("proxie" -> "Proxie") in testing.
# Returns (list_type, display, targets, data) or (None, error, None, None).
def handle_query(user_input):
    _last_results.clear()
    _agent.invoke({"messages": [{"role": "user", "content": user_input}]})

    if not _last_results.get("type"):
        return None, "Sorry, I couldn't understand that. Try rephrasing?", None, None

    return (
        _last_results["type"],
        _last_results["display"],
        _last_results["targets"],
        _last_results["data"],
    )


# Pulls from spotipy to queue the selected songs. selected is a list of
# {"name", "artist"} dicts.
def queue_songs(selected):
    for song in selected:
        track = search_track(song["name"], song["artist"])
        if not track:
            print(f"  Couldn't find '{song['name']}' by {song['artist']} on Spotify.")
            continue

        if queue_track(track["uri"]):
            print(f"  Queued: {track['name']} by {track['artists'][0]['name']}")


# Step 5's second hop: artist -> their top tracks. Called directly rather than
# through the agent — a selection isn't a natural-language query.
# Returns (display, targets, data) or (None, None, None) on failure.
def expand_artist(artist_name):
    resp = get_artist_top_tracks(artist_name, limit=5)
    if "error" in resp:
        print(f"Last.fm: {resp['message']}")
        return None, None, None

    tracks = resp.get("toptracks", {}).get("track", [])
    if not tracks:
        print(f"No top tracks found for {artist_name}.")
        return None, None, None

    return build_song_list(tracks)


# Main loop: tracks which list is currently on screen and routes input as
# either a new search or a selection from that list.
def main():
    print("How may I assist you in finding similar artists or songs?")
    print("(type 'quit' to exit, 'new' to start a fresh search)")

    current_type = None
    current_display = None
    current_targets = None
    current_data = None

    while True:
        user_input = input("\n> ").strip()

        if user_input.lower() in ("quit", "exit"):
            break

        if user_input.lower() == "new":
            current_type = None
            print("What are you looking for?")
            continue

        # No list on screen -> treat input as a new search
        if current_type is None:
            list_type, display, targets, data = handle_query(user_input)
            if list_type is None:
                print(display)  # error message
                continue

            current_type, current_display, current_targets, current_data = list_type, display, targets, data
            show_list(current_type, current_display)
            continue

        # A list is on screen -> try selection first
        indices, error = parse_selection(user_input, current_display, match_targets=current_targets)

        if error:
            # Might be a new search rather than a bad selection
            looks_like_search = len(user_input.split()) >= 3
            if looks_like_search:
                list_type, display, targets, data = handle_query(user_input)
                if list_type is not None:
                    current_type, current_display, current_targets, current_data = list_type, display, targets, data
                    show_list(current_type, current_display)
                    continue
                print(f"[retry failed] {display}")
                continue

            print(error)
            continue

        if current_type == "similar_artists":
            if len(indices) > 1:
                print("Pick one artist at a time for now.")
                continue

            artist_name = current_data[indices[0]]
            display, targets, data = expand_artist(artist_name)
            if display is None:
                continue

            current_type, current_display, current_targets, current_data = "top_tracks", display, targets, data
            show_list(current_type, current_display)

        else:  # similar_songs or top_tracks -> queue them
            selected = [current_data[i] for i in indices]
            queue_songs(selected)


if __name__ == "__main__":
    main()