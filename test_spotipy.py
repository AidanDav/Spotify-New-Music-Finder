import spotipy
from spotipy.oauth2 import SpotifyOAuth

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id="SPOTIFY API KEY HERE",
    client_secret="SECRET API KEY HERE",
    redirect_uri="callback https",
    scope="user-top-read user-read-recently-played"
))

top_artists = sp.current_user_top_artists(limit=10)
for artist in top_artists['items']:
    print(artist['name'])