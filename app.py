import threading
from collections import deque

import streamlit as st

from lastfm_agent import build_agent, _last_results
from lastfm_client import get_artist_top_tracks
from spotify_client import search_track, queue_track
from playback_poller import PlaybackPoller
from database import init_db, log_feedback, filter_disliked

st.set_page_config(page_title="Music Discovery", page_icon="\U0001F3B5")

# ---------------------------------------------------------------------------
# Process-wide singletons.
# Streamlit reruns this whole script top-to-bottom on every interaction, but
# these are cached with st.cache_resource so they're built once per Python
# process rather than once per rerun — same reasoning as "_agent built once
# at import" in the old main.py, just using Streamlit's mechanism for it.
# ---------------------------------------------------------------------------
init_db()


@st.cache_resource
def get_agent():
    return build_agent()


_agent = get_agent()

# The poller thread is shared across the whole app (one background thread,
# not one per browser tab), so it can't write into st.session_state safely —
# session_state belongs to a specific user session and isn't meant to be
# touched from a thread that isn't handling that session's rerun. Instead
# the poller writes into a plain module-level deque guarded by a lock, and
# the feedback_panel fragment below drains it into session_state on its own
# timer. This mirrors the CLI's _pending_events/_pending_lock pattern.
@st.cache_resource
def get_event_bus():
    """A lock + deque bundled into one cache_resource-guaranteed singleton.
    This can't be a plain module-level global — Streamlit re-executes
    top-level script code on every FULL rerun (e.g. whenever the Queue
    button below is clicked, which isn't inside a fragment), which would
    silently rebind a global `_pending_events = deque()` to a brand-new,
    empty deque each time. The poller thread's callbacks get wired up once,
    inside get_poller()'s cached body, the very first time the app loads —
    they'd keep writing into that FIRST deque forever, while the rest of
    the app moved on to reading whichever new one the latest rerun created.
    Events would be recorded but never surface. Bundling both here and
    having every consumer fetch them via this same cached function
    guarantees they all share the exact same objects regardless of reruns."""
    return {"lock": threading.Lock(), "events": deque()}


@st.cache_resource
def get_poller():
    bus = get_event_bus()

    def on_finished(track_info):
        with bus["lock"]:
            bus["events"].append(("finished", track_info))

    def on_skipped(track_info):
        with bus["lock"]:
            bus["events"].append(("skipped", track_info))

    poller = PlaybackPoller(on_finished=on_finished, on_skipped=on_skipped)
    poller.start()
    return poller


_event_bus = get_event_bus()
_poller = get_poller()

# ---------------------------------------------------------------------------
# Session state — this replaces main.py's current_type/current_display/
# current_targets/current_data loop variables. Unlike the module-level
# singletons above, this genuinely is per-browser-tab.
#
# `history` holds one entry per user query, each rendered as a user chat
# bubble followed by an assistant bubble with that query's results — so
# results stay attached to the query that produced them instead of a single
# current_type/current_data pair that the next query would overwrite.
# ---------------------------------------------------------------------------
_defaults = {
    "history": [],           # list of {"query", "list_type", "data", "error"}
    "log": [],               # list of ("info" | "error", message)
    "feedback_queue": [],    # tracks awaiting a like/dislike click
}
for _key, _value in _defaults.items():
    if _key not in st.session_state:
        st.session_state[_key] = _value


# ---------------------------------------------------------------------------
# Backend helpers — thin wrappers around the same modules the CLI used.
# ---------------------------------------------------------------------------
def build_song_list(tracks):
    data = [{"name": t["name"], "artist": t["artist"]["name"]} for t in tracks]
    return filter_disliked(data)


def handle_query(user_input):
    """Route free text through the LangChain agent. Returns (list_type, data)
    on success, or (None, error_message) on failure."""
    _last_results.clear()
    result = _agent.invoke({"messages": [{"role": "user", "content": user_input}]})

    if not _last_results.get("type"):
        # Nothing got stashed by a tool call. Surface the agent's own final
        # reply if it has one — the tool functions in lastfm_agent.py
        # already return specific reasons (e.g. "No similar artists found
        # for X"), so this distinguishes "Last.fm found nothing" from a
        # genuine parse failure, instead of always showing one generic
        # fallback for both.
        final_message = None
        if result.get("messages"):
            final_message = getattr(result["messages"][-1], "content", None)
        return None, (final_message or "Sorry, I couldn't understand that. Try rephrasing?")

    return _last_results["type"], _last_results["data"]

# ---------------------------------------------------------------------------
# Queueing / feedback helpers — these are the same as the CLI's queue_song() and expand_artist().
# ---------------------------------------------------------------------------
def expand_artist(artist_name):
    resp = get_artist_top_tracks(artist_name, limit=5)
    if "error" in resp:
        return None, f"Last.fm: {resp['message']}"

    tracks = resp.get("toptracks", {}).get("track", [])
    if not tracks:
        return None, f"No top tracks found for {artist_name}."

    data = build_song_list(tracks)
    if not data:
        return None, f"No top tracks found for {artist_name} (filtered by past dislikes)."

    return data, None

# ---------------------------------------------------------------------------
# Queueing / feedback helpers — these are the same as the CLI's queue_song() and expand_artist().
# ---------------------------------------------------------------------------
def queue_song(song, source_type):
    track = search_track(song["name"], song["artist"])
    if not track:
        return None, f"Couldn't find '{song['name']}' by {song['artist']} on Spotify."

    if not queue_track(track["uri"]):
        return None, "No active Spotify device — open Spotify and start playing something first."

    queued_name = track["name"]
    queued_artist = track["artists"][0]["name"]
    _poller.watch(track["uri"], name=queued_name, artist=queued_artist, source_type=source_type)
    return {"name": queued_name, "artist": queued_artist}, None


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("\U0001F3B5 Music Discovery")

if st.sidebar.button("New search"):
    st.session_state.history = []
    st.rerun()


# Auto-refreshing panel: drains any finished/skipped tracks out of the
# module-level poller queue and renders like/dislike buttons for each.
# run_every makes this fragment rerun on its own timer, independent of user
# interaction — this is what makes feedback appear without pressing
# anything first, replacing the "drain at the top of input()'s loop" trick
# the CLI needed.
@st.fragment(run_every=3)
def feedback_panel():
    with _event_bus["lock"]:
        while _event_bus["events"]:
            st.session_state.feedback_queue.append(_event_bus["events"].popleft())

    if not st.session_state.feedback_queue:
        return

    st.subheader("How was it?")
    remaining = []
    # Render each finished/skipped track with like/dislike buttons. If the user
    # clicks one, log it to the database; otherwise keep it in the queue for
    for event, track_info in st.session_state.feedback_queue:
        verb = "finished playing" if event == "finished" else "was skipped"
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"**{track_info['name']}** by {track_info['artist']} — {verb}")

        key_base = f"{track_info['name']}_{track_info['artist']}"
        liked = col2.button("\U0001F44D", key=f"like_{key_base}")
        disliked = col3.button("\U0001F44E", key=f"dislike_{key_base}")
        # If the user clicked either button, log the feedback to the database; otherwise, keep it in the queue for the next run.
        if liked or disliked:
            log_feedback(
                track_info["name"],
                track_info["artist"],
                "liked" if liked else "disliked",
                source_type=track_info.get("source_type"),
            )
        else:
            remaining.append((event, track_info))

    st.session_state.feedback_queue = remaining

# ---------------------------------------------------------------------------
# streamlit chat UI — this is the main body of the app, rendering the query input and the history of queries/results.
# ---------------------------------------------------------------------------
def render_results(turn, key_prefix):
    """Renders one turn's results inside an assistant chat bubble. key_prefix
    must be unique per turn so widget keys don't collide across history."""
    if turn["error"]:
        st.error(turn["error"])
        return

    list_type, data = turn["list_type"], turn["data"]
    # The following is a bit of a hack: the agent's tool functions return a list of dicts for songs, 
    # but a list of strings for artists. This is because the agent doesn't need to know the artist names for similar artists, 
    # but it does need to know the song names and artist names for similar songs. 
    # So we have to handle these two cases separately when rendering the results.
    if list_type == "similar_artists":
        st.subheader("Similar artists")
        for artist_name in data:
            if st.button(f"See top tracks \u2192 {artist_name}", key=f"{key_prefix}_artist_{artist_name}"):
                tracks, error = expand_artist(artist_name)
                if error:
                    st.session_state.log.append(("error", error))
                else:
                    st.session_state.history.append({
                        "query": f"Top tracks for {artist_name}",
                        "list_type": "top_tracks",
                        "data": tracks,
                        "error": None,
                    })
                st.rerun()

    elif list_type in ("similar_songs", "top_tracks", "liked_songs"):
        st.subheader("Your liked songs" if list_type == "liked_songs" else "Songs")
        for song in data:
            col1, col2 = st.columns([4, 1])
            col1.write(f"{song['name']} by {song['artist']}")
            if col2.button("Queue", key=f"{key_prefix}_queue_{song['name']}_{song['artist']}"):
                queued, error = queue_song(song, list_type)
                if error:
                    st.session_state.log.append(("error", error))
                else:
                    st.session_state.log.append(("info", f"Queued: {queued['name']} by {queued['artist']}"))
                st.rerun()


# st.chat_input always renders pinned to the bottom of the page regardless
# of where it's called from, so it's read here — before the history is
# rendered below — meaning a freshly submitted query's turn (appended to
# history immediately) shows up in the same run without an extra rerun.
query = st.chat_input("Ask for similar artists, similar songs, or an artist's top tracks")

if query:
    list_type, payload = handle_query(query)
    if list_type is None:
        st.session_state.history.append({"query": query, "list_type": None, "data": None, "error": payload})
    else:
        st.session_state.history.append({"query": query, "list_type": list_type, "data": payload, "error": None})
# Render the history of queries and results. Each turn is a user query followed by an assistant response, 
# which may include buttons for further actions (like seeing top tracks or queuing a song).
for idx, turn in enumerate(st.session_state.history):
    with st.chat_message("user"):
        st.write(turn["query"])
    with st.chat_message("assistant"):
        render_results(turn, key_prefix=str(idx))

for kind, message in st.session_state.log[-5:]:
    (st.error if kind == "error" else st.info)(message)

st.divider()
feedback_panel()