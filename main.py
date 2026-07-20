import threading
from collections import deque

from lastfm_agent import build_agent, _last_results
from lastfm_client import get_artist_top_tracks
from spotify_client import search_track, queue_track
from playback_poller import PlaybackPoller
from parsing import parse_selection
from feedback_parser import parse_feedback
from database import init_db, log_feedback, filter_disliked

INTRO_TEXT = {
    "similar_songs": "Here are {count} songs you might like. Want me to queue any? Name or number works.",
    "similar_artists": "Here are {count} artists you might like. Want to see popular songs from any of them?",
    "top_tracks": "Here are {count} popular songs from that artist. Want me to queue any?",
}

# Built once at import — rebuilding per query would be wasteful.
_agent = build_agent()

# ---------------------------------------------------------------------------
# Playback polling wiring
# ---------------------------------------------------------------------------
# The poller runs on its own thread and has no way to safely call input()
# itself (it'd race with the main thread's input() for the next command).
# So callbacks just stash the event; the main loop drains it at the next
# natural pause point and asks for feedback there, on the main thread.
_pending_events = deque()
_pending_lock = threading.Lock()


def _on_track_finished(track_info):
    with _pending_lock:
        _pending_events.append(("finished", track_info))


def _on_track_skipped(track_info):
    with _pending_lock:
        _pending_events.append(("skipped", track_info))


_poller = PlaybackPoller(on_finished=_on_track_finished, on_skipped=_on_track_skipped)


def _drain_playback_events():
    """Report on and collect feedback for any tracks that finished or were
    skipped since the last time this was checked. source_type travels with
    each track's watch() metadata, so this doesn't depend on whatever list
    happens to be on screen right now — the user may have moved on to a
    totally different search since the track was queued."""
    with _pending_lock:
        events = list(_pending_events)
        _pending_events.clear()

    for event, track_info in events:
        verb = "finished playing" if event == "finished" else "was skipped"
        print(f"\n\U0001F3B5 '{track_info['name']}' by {track_info['artist']} {verb}.")
        collect_feedback([track_info], source_type=track_info.get("source_type"))


# Displays a list to the user with a friendly intro. list_type is a key in
# INTRO_TEXT, display is the list of strings to show.
def show_list(list_type, display):
    print("\n" + INTRO_TEXT[list_type].format(count=len(display)))
    for i, name in enumerate(display, 1):
        print(f"  {i}. {name}")


# Returns (display, targets, data) for a list of Last.fm track dicts,
# with any most-recently-disliked tracks filtered out first. This is the
# non-agent path (expand_artist), so it needs its own filtering — the
# agent tools in lastfm_agent.py filter independently on their side.
def build_song_list(tracks):
    data = [{"name": t["name"], "artist": t["artist"]["name"]} for t in tracks]
    data = filter_disliked(data)
    display = [f"{d['name']} by {d['artist']}" for d in data]
    targets = [d["name"] for d in data]
    return display, targets, data


# Handle query routed through the LangChain agent. The agent's prose answer is
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


# Pulls from spotipy to queue the selected songs, then registers each
# successfully-queued track with the poller so feedback gets asked once
# it actually finishes or gets skipped — not right away, since queueing
# a track doesn't mean the user has heard it yet.
# selected is a list of {"name", "artist"} dicts. source_type travels
# with each track so _drain_playback_events knows where it came from
# later, even if the on-screen list has since changed.
def queue_songs(selected, source_type):
    queued = []

    for song in selected:
        track = search_track(song["name"], song["artist"])
        if not track:
            print(f"  Couldn't find '{song['name']}' by {song['artist']} on Spotify.")
            continue

        if queue_track(track["uri"]):
            queued_name = track["name"]
            queued_artist = track["artists"][0]["name"]
            print(f"  Queued: {queued_name} by {queued_artist}")
            queued.append({"name": queued_name, "artist": queued_artist})
            _poller.watch(
                track["uri"],
                name=queued_name,
                artist=queued_artist,
                source_type=source_type,
            )

    if queued:
        _poller.start()  # no-op if already running

    return queued


# Ask for per-song feedback on whatever actually finished or was skipped,
# parse it (deterministic first, LLM fallback for the leftovers), and
# persist whatever was understood. source_type records where these songs
# came from (e.g. "similar_songs", "top_tracks") for future recommendation
# use.
def collect_feedback(queued, source_type):
    if not queued:
        return

    targets = [f"{song['name']} by {song['artist']}" for song in queued]

    print("How was it?" if len(targets) == 1 else "\nHow were these?")
    for i, target in enumerate(targets, 1):
        print(f"  {i}. {target}")

    feedback_input = input("> ").strip()

    # Treat a blank answer or an explicit skip as declining to give
    # feedback at all — not as "disliked everything".
    if not feedback_input or feedback_input.lower() in ("skip", "no", "n/a", "none"):
        return

    verdicts = parse_feedback(feedback_input, targets)

    for i, song in enumerate(queued):
        target = targets[i]
        opinion = verdicts.get(i)
        if opinion:
            log_feedback(song["name"], song["artist"], opinion, source_type=source_type)
            print(f"  Logged: {target} — {opinion}")
        else:
            print(f"  Not sure how you felt about {target} — skipping")


# Artist -> their top tracks. Called directly rather than
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

    display, targets, data = build_song_list(tracks)
    if not display:
        print(f"No top tracks found for {artist_name} (results were filtered out based on past dislikes).")
        return None, None, None

    return display, targets, data


# Main loop: tracks which list is currently on screen and routes input as
# either a new search or a selection from that list.
def main():
    init_db()

    print("How may I assist you in finding similar artists or songs?")
    print("(type 'quit' to exit, 'new' to start a fresh search)")

    current_type = None
    current_display = None
    current_targets = None
    current_data = None

    while True:
        # Report on any tracks that finished/were skipped since the last
        # prompt, before showing the next one — this is what makes
        # feedback event-driven instead of "ask right after queueing".
        _drain_playback_events()

        user_input = input("\n> ").strip()

        if user_input.lower() in ("quit", "exit"):
            _poller.stop()
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
            queue_songs(selected, source_type=current_type)
            # No collect_feedback() call here anymore — it now happens
            # in _drain_playback_events() once these tracks actually
            # finish or get skipped.


if __name__ == "__main__":
    main()