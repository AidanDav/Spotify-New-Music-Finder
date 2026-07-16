import requests

LASTFM_API_KEY = "YOUR API KEY HERE"

def get_similar_songs(track_name, artist_name, limit=10):
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "track.getsimilar",
        "track": track_name,
        "artist": artist_name,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit,
        "autocorrect": 1
    }
    response = requests.get(url, params=params)
    return response.json()


if __name__ == "__main__":
    result = get_similar_songs("Californication", "Red Hot Chili Peppers", limit=5)

    if "error" in result:
        print(f"Error: {result['message']}")
    else:
        for track in result.get("similartracks", {}).get("track", []):
            print(f"  - {track['name']} by {track['artist']['name']} (similarity: {track['match']})")
