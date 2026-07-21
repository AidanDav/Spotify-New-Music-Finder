import threading
from spotify_client import get_current_playback

# How far into a track (as a fraction of duration) it needs to have gotten
# before a track-change counts as "finished" rather than "skipped".
FINISHED_THRESHOLD = 0.90

# How often to ask Spotify what's playing, in seconds. Spotify has no
# push/webhook for playback state — this has to poll. No reason to poll
# faster than a human could plausibly hit "next".
POLL_INTERVAL_SECONDS = 10


class PlaybackPoller:
    """
    Background thread that watches Spotify's currently-playing track and
    fires callbacks when a WATCHED song finishes naturally, gets skipped,
    or playback stops outright.

    Only tracks registered via watch() are reported on — anything else
    the user plays (their own choice, another app, browsing their library)
    is silently ignored, so this doesn't nag about unrelated listening.

    Thread safety: this thread only calls get_current_playback() (a GET).
    It never calls queue_track/search_track, so it doesn't race with the
    main thread's writes. The watched-tracks dict is guarded by a lock
    since both threads touch it (main thread adds via watch(), this
    thread removes via _handle_track_change()).
    """

    def __init__(self, on_finished=None, on_skipped=None, poll_interval=POLL_INTERVAL_SECONDS):
        self._on_finished = on_finished
        self._on_skipped = on_skipped
        self._poll_interval = poll_interval

        self._watched = {}  # uri -> metadata dict (name, artist, source_type, ...)
        self._lock = threading.Lock()

        self._last_uri = None
        self._last_progress_ms = 0
        self._last_duration_ms = None

        self._stop_event = threading.Event()
        self._thread = None
    # The watch() method registers a track to be monitored. 
    # It takes the track's URI and any associated metadata (like name, artist, source_type) 
    # and stores them in the _watched dictionary. The method acquires a lock to ensure thread 
    # safety while modifying the shared _watched dictionary.
    def watch(self, uri, **metadata):
        """Register a queued track so the poller reports on it when it changes.
        metadata (e.g. name, artist, source_type) is passed back verbatim
        to the on_finished/on_skipped callback."""
        with self._lock:
            self._watched[uri] = metadata
    # The start() method starts the background polling thread. 
    # It checks if the thread is already running, and if not, it clears the stop event, 
    # creates a new thread targeting the _run() method, and starts it as a daemon thread.
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    # The stop() method stops the background polling thread.
    # It sets the stop event, and if the thread is running, it joins the 
    # thread with a timeout to ensure it terminates gracefully.
    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._poll_interval + 1)
    # The _run() method is the main loop of the background thread.
    # It continuously polls the current playback state by calling _poll_once()
    # until the stop event is set. If an exception occurs during polling, it prints an error message
    # and continues to the next cycle. The thread waits for the specified poll interval before the next iteration.
    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as e:
                # A transient network/API hiccup shouldn't kill the thread —
                # skip this cycle, try again next tick.
                print(f"\n[poller] playback check failed: {e}")
            self._stop_event.wait(self._poll_interval)
    # The _poll_once() method checks the current playback state and determines if a track has changed.
    # It retrieves the current playback information, including the track URI, progress, and duration.
    # If the current track URI differs from the last recorded URI, it calls _handle_track_change()
    # to handle the change and update the last recorded URI, progress, and duration.
    def _poll_once(self):
        playback = get_current_playback()

        current_uri = None
        current_progress = 0
        current_duration = None

        if playback and playback.get("item"):
            current_uri = playback["item"]["uri"]
            current_progress = playback.get("progress_ms") or 0
            current_duration = playback["item"].get("duration_ms")

        previous_uri = self._last_uri

        # Track changed, or playback stopped entirely while we were
        # watching something — both mean "the previous track is done".
        if previous_uri is not None and current_uri != previous_uri:
            self._handle_track_change(previous_uri)

        self._last_uri = current_uri
        self._last_progress_ms = current_progress
        self._last_duration_ms = current_duration
    # The _handle_track_change() method is called when a track change is detected.
    # It checks if the previous track was being watched and determines if it finished or was skipped
    # based on the last recorded progress and duration. It then calls the appropriate callback
    # (on_finished or on_skipped) with the track's metadata. The method acquires a lock to ensure
    # thread safety while accessing the shared _watched dictionary.
    def _handle_track_change(self, previous_uri):
        with self._lock:
            track_info = self._watched.pop(previous_uri, None)

        if track_info is None:
            return  # not a track we're watching — ignore

        finished = False
        if self._last_duration_ms:
            finished = (self._last_progress_ms / self._last_duration_ms) >= FINISHED_THRESHOLD

        callback = self._on_finished if finished else self._on_skipped
        if callback:
            callback(track_info)