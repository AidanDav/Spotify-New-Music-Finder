import os
import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    scope="user-modify-playback-state user-read-playback-state"
))

track_name = "Stop Sign"
artist_name = "DICE"
query = f'track:"{track_name}" artist:"{artist_name}"'

results = sp.search(q=query, type="track", limit=1)
tracks = results['tracks']['items']

if not tracks:
    print(f"No track found for query: {query}")
else:
    track = tracks[0]
    track_uri = track['uri']
    print(f"Found: {track['name']} by {track['artists'][0]['name']} ({track_uri})")

    sp.add_to_queue(uri=track_uri)
    print("Added to queue.")