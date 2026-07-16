import ollama
import json
import requests

LASTFM_API_KEY = "YOUR API KEY HERE"

def extract_query(user_message):
    extraction_prompt = f"""Determine whether this user request is asking for similar SONGS or similar ARTISTS, then extract the relevant details.

Rules:
- If they mention a specific song title, this is "song" type. Extract the song title and artist if mentioned (artist can be empty string if not given).
- If they mention only an artist/band name with no specific song, this is "artist" type. Extract the artist name.
- Correct obvious typos to the most likely intended title/name.

User request: "{user_message}"

Respond with ONLY valid JSON, nothing else, in ONE of these two exact formats:
For songs: {{"type": "song", "song": "song title here", "artist": "artist name or empty string"}}
For artists: {{"type": "artist", "artist": "artist name here"}}"""

    response = ollama.chat(
        model='mistral',
        messages=[{'role': 'user', 'content': extraction_prompt}]
    )

    raw_output = response['message']['content'].strip()

    if not raw_output.startswith("{"):
        start = raw_output.find("{")
        end = raw_output.rfind("}") + 1
        raw_output = raw_output[start:end]

    try:
        parsed = json.loads(raw_output)
        return parsed
    except json.JSONDecodeError:
        print(f"Failed to parse Mistral's output as JSON: {raw_output}")
        return None



def get_similar_artists(artist_name, limit=10):
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "artist.getsimilar",
        "artist": artist_name,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit
    }
    response = requests.get(url, params=params)
    return response.json()

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
    while True:
        user_input = input("\nWhat are you looking for? (or type 'quit')\n> ")

        if user_input.lower() == "quit":
            break

        result = extract_query(user_input)

        if not result:
            print("Couldn't extract info, try rephrasing.")
            continue

        if result["type"] == "song":
            ans = get_similar_songs(result["song"], result["artist"], limit=5)
            if "error" in ans:
                print(f"Error: {ans['message']}")
            else:
                for track in ans.get("similartracks", {}).get("track", []):
                    print(f"  - {track['name']} by {track['artist']['name']} (similarity: {track['match']})")
        elif result["type"] == "artist":
            #We get the similar artists from Last.fm
            ans = get_similar_artists(result["artist"], limit=5)
            #Error handling for Last.fm API response
            if "error" in ans:
                print(f"Couldn't find similar artists for '{result['artist']}' (Last.fm error: {ans['message']}).")
            #If no error, we are able to print out similar artists
            else:
                print(f"[ARTIST mode] Similar artists to '{result['artist']}':")
                for artist in ans["similarartists"]["artist"]:
                    #Prints the artists and the similarity score to the user in a readable format
                    print(f"  - {artist['name']} (similarity: {artist['match']})")
        else:
            print(f"Unrecognized type: {result}")