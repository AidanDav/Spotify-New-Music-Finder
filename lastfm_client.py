import requests
from config import LASTFM_API_KEY

BASE_URL = "https://ws.audioscrobbler.com/2.0/"

#LastFM API functions to get similar artists and songs

#Function to get similar artists from Last.fm API with artist.getsimilar method
#Set initial limit to 10, can be changed by passing limit parameter
def get_similar_artists(artist_name, limit=10):
    params = {
        "method": "artist.getsimilar",
        "artist": artist_name,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit
    }
    response = requests.get(BASE_URL, params=params)
    return response.json()

#Function to get similar songs from Last.fm API with track.getsimilar method
#Set initial limit to 10, can be changed by passing limit parameter
def get_similar_songs(track_name, artist_name, limit=10):
    params = {
        "method": "track.getsimilar",
        "track": track_name,
        "artist": artist_name,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit * 3,      # over-fetch to survive filtering
        "autocorrect": 1
    }
    response = requests.get(BASE_URL, params=params)
    data = response.json()

    if "error" in data:
        return data

    all_tracks = data.get("similartracks", {}).get("track", [])

    filtered = [
        t for t in all_tracks
        if t["artist"]["name"].strip().lower() != artist_name.strip().lower()
    ]

    data["similartracks"]["track"] = filtered[:limit]
    return data


def get_artist_top_tracks(artist_name, limit=10):
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "artist.gettoptracks",
        "artist": artist_name,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit
    }
    response = requests.get(url, params=params)
    return response.json()