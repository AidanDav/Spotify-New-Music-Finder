import ollama

# Fake listening history — stand-in for real Spotify data later
fake_listening_history = {
    "top_artists": ["DICE", "The Kilans", "Rec Hall"],
    "recent_tracks": ["Stop Sign", "Why Is It Light Out?", "She Doesn't Get It"]
}

prompt = f"""You are a knowledgeable music recommendation assistant.

Here is a user's listening history:
Top artists: {', '.join(fake_listening_history['top_artists'])}
Recently played tracks: {', '.join(fake_listening_history['recent_tracks'])}

Based on this listening history, recommend similar music in two categories:

1. "Likely already know" — artists/songs that are popular enough the user has probably heard of them already, but fit their taste.
2. "Deeper cuts" — lesser-known artists/songs that share a similar sound, mood, or style, but are less mainstream and the user likely hasn't discovered yet.

For each recommendation, briefly explain WHY it fits their taste (shared genre, mood, era, instrumentation, etc.).

Format your response with clear headers for each category."""

response = ollama.chat(
    model='mistral',
    messages=[{'role': 'user', 'content': prompt}]
)

print(response['message']['content'])