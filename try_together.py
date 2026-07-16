import spotipy
from spotipy.oauth2 import SpotifyOAuth

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id="SPOTIFY API KEY HERE",
    client_secret="SECRET KEY HERE",
    redirect_uri="callback https",
    scope="user-modify-playback-state user-read-playback-state"
))

query = "Getaway Car - Taylor Swift"
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
