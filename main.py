from mistral_client import extract_query
from lastfm_client import get_similar_songs, get_similar_artists, get_artist_top_tracks
from spotify_client import search_track, queue_track
from parsing import parse_selection

INTRO_TEXT = {
    "similar_songs": "Here are {count} songs you might like. Want me to queue any? Name or number works.",
    "similar_artists": "Here are {count} artists you might like. Want to see popular songs from any of them?",
    "top_tracks": "Here are {count} popular songs from that artist. Want me to queue any?",
}


def show_list(list_type, display):
    print("\n" + INTRO_TEXT[list_type].format(count=len(display)))
    for i, name in enumerate(display, 1):
        print(f"  {i}. {name}")


def build_song_list(tracks):
    """Returns (display, targets, track_data) for a list of Last.fm track dicts."""
    display = [f"{t['name']} by {t['artist']['name']}" for t in tracks]
    targets = [t["name"] for t in tracks]
    data = [{"name": t["name"], "artist": t["artist"]["name"]} for t in tracks]
    return display, targets, data


def handle_query(user_input):
    """Steps 2-4. Returns (list_type, display, targets, data) or (None, error, None, None)."""
    result = extract_query(user_input)
    if not result or "type" not in result:
        return None, "Sorry, I couldn't understand that. Try rephrasing?", None, None

    if result["type"] == "song":
        artist = result.get("artist", "")
        if not artist:
            return None, "I need an artist name to find similar songs.", None, None

        resp = get_similar_songs(result["song"], artist, limit=5)
        if "error" in resp:
            return None, f"Last.fm: {resp['message']}", None, None

        tracks = resp.get("similartracks", {}).get("track", [])
        if not tracks:
            return None, "No similar tracks found.", None, None

        display, targets, data = build_song_list(tracks)
        return "similar_songs", display, targets, data

    elif result["type"] == "artist":
        resp = get_similar_artists(result["artist"], limit=5)
        if "error" in resp:
            return None, f"Last.fm: {resp['message']}", None, None

        artists = resp.get("similarartists", {}).get("artist", [])
        if not artists:
            return None, "No similar artists found.", None, None

        names = [a["name"] for a in artists]
        return "similar_artists", names, None, names

    return None, f"Unknown type: {result}", None, None


def queue_songs(selected):
    """Step 7. selected is a list of {"name", "artist"} dicts."""
    for song in selected:
        track = search_track(song["name"], song["artist"])
        if not track:
            print(f"  Couldn't find '{song['name']}' by {song['artist']} on Spotify.")
            continue

        if queue_track(track["uri"]):
            print(f"  Queued: {track['name']} by {track['artists'][0]['name']}")


def expand_artist(artist_name):
    """Step 5's second hop: artist -> their top tracks."""
    resp = get_artist_top_tracks(artist_name, limit=5)
    if "error" in resp:
        print(f"Last.fm: {resp['message']}")
        return None, None, None

    tracks = resp.get("toptracks", {}).get("track", [])
    if not tracks:
        print(f"No top tracks found for {artist_name}.")
        return None, None, None

    return build_song_list(tracks)


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

        # A list is on screen -> treat input as a selection
        indices, error = parse_selection(user_input, current_display, match_targets=current_targets)
        if error:
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