import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope="user-modify-playback-state user-read-playback-state"
))

#Function to search for a track on Spotify and return the top match
#Uses field filters (track:"..." artist:"...") instead of a plain keyword
#search so we match the exact song rather than Spotify's loose text search.
def search_track(track_name, artist_name):
    query = f'track:"{track_name}" artist:"{artist_name}"'
    results = sp.search(q=query, type="track", limit=1)
    tracks = results["tracks"]["items"]

    if not tracks:
        return None

    return tracks[0]

#Function to queue a track by URI on the user's active device.
#Spotify returns a 404 with reason NO_ACTIVE_DEVICE if nothing is currently
#playing, which we surface as a clear failure instead of an uncaught exception.
def queue_track(track_uri):
    try:
        sp.add_to_queue(uri=track_uri)
        return True
    except SpotifyException as e:
        if e.reason == "NO_ACTIVE_DEVICE":
            print("No active Spotify device found. Open Spotify and start playing something, then try again.")
            return False
        raise

#Function to get the user's current playback state (None if nothing is playing)
def get_current_playback():
    return sp.current_playback()
