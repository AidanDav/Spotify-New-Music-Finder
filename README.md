# Spotify-New-Music-Finder

# Music Discovery Agent

A conversational music discovery tool that finds similar artists, similar songs,
and an artist's top tracks via Last.fm, lets you queue picks straight to your
active Spotify device, and learns your taste over time — like/dislike feedback
is collected automatically once a queued song actually finishes playing or
gets skipped, not just right after you queue it.

## Features

- **Natural-language search** — "artists like DICE", "songs similar to Stop Sign
  by DICE", "what are Radiohead's most popular songs" — powered by a local LLM
  (Ollama, `qwen2.5`) acting as a tool-calling agent over the Last.fm API.
- **One-click queueing** to your currently active Spotify device.
- **Automatic feedback collection.** A background poller watches Spotify
  playback and detects when a queued track finishes naturally versus gets
  skipped early, then prompts for a 👍/👎 at that moment — not immediately
  after queueing, before you've actually heard it.
- **Feedback-aware recommendations.** Disliked songs are filtered out of
  future Last.fm results automatically.
- **"Show me my liked songs"** — ask the agent to pull up your own feedback
  history and replay a favorite.

## How it works

1. Ask for similar artists, similar songs, or an artist's top tracks.
2. Click a result to queue it (or, for an artist result, drill into their top
   tracks first).
3. Keep browsing or searching — no need to wait around.
4. Once a queued song finishes or gets skipped, a feedback prompt appears with
   👍/👎 buttons. Your answer is logged and shapes future recommendations.

## Project structure

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI — the main way to run this. |
| `main.py` | Original terminal/CLI version. Still works, but selection is by typed number/name instead of buttons. |
| `lastfm_agent.py` | LangChain agent + tool definitions (similar artists/songs, top tracks, liked songs) that wrap `lastfm_client.py`. |
| `lastfm_client.py` | Thin wrapper around the Last.fm API. |
| `spotify_client.py` | Spotify search/queue/playback-state calls via `spotipy`. |
| `playback_poller.py` | Background thread that polls Spotify playback and detects when a watched track finishes or is skipped. |
| `database.py` | SQLite-backed feedback storage (liked/disliked songs, liked artists, filtering helpers). |
| `parsing.py` | Text-selection and deterministic feedback-keyword parsing, used by the CLI (`main.py`). Not used by the Streamlit UI, which selects via buttons. |
| `feedback_parser.py` | LLM fallback for free-text feedback the deterministic parser can't confidently resolve. Used by the CLI only. |
| `config.py` | Loads API keys/secrets from `.env`. |

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) installed locally, with the `qwen2.5` model pulled:
  ```
  ollama pull qwen2.5
  ```
- A [Spotify Premium](https://www.spotify.com/premium/) account — queueing and
  playback-state endpoints require Premium, and a device (the Spotify app,
  desktop or mobile) needs to be open and actively playing something for
  queueing to work.
- A [Spotify Developer app](https://developer.spotify.com/dashboard) (for a
  client ID/secret and a registered redirect URI).
- A [Last.fm API key](https://www.last.fm/api/account/create).

## Setup

1. **Clone and create a virtual environment:**
   ```
   git clone <this-repo>
   cd <this-repo>
   python -m venv venv
   source venv/bin/activate   # venv\Scripts\activate on Windows
   ```

2. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

3. **Create a `.env` file** in the project root:
   ```
   LASTFM_API_KEY=your_lastfm_api_key
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
   ```
   The redirect URI must exactly match one registered in your Spotify
   Developer Dashboard app settings.

4. **First run will open a browser window** for Spotify OAuth — log in and
   approve access. `spotipy` caches the resulting token locally, so this is a
   one-time step per machine (until the token expires or is revoked).

## Running it

**Streamlit UI (recommended):**
```
streamlit run app.py
```
Opens in your browser, usually at `http://localhost:8501`.

**Terminal/CLI version:**
```
python main.py
```
Type `new` to start a fresh search, `quit`/`exit` to leave. Select results by
number or by typing the name.

## Known limitations

- **Single-user, local by design.** There's no multi-user auth — the Spotify
  OAuth flow and the local SQLite feedback database both assume one person
  using their own machine.
- **Polling has a delay.** Playback state is checked every few seconds, not
  instantly — expect a short lag between a song finishing/being skipped and
  the feedback prompt appearing.
- **Queueing requires an active device.** If nothing is currently playing on
  any Spotify device, queueing will fail with a message asking you to start
  playback first.
- **Ollama runs locally.** `qwen2.5` needs to be pulled and Ollama needs to be
  running (`ollama serve`, or it may already run as a background service)
  before either `app.py` or `main.py` will work.

## Roadmap

- `user-top-read` OAuth scope, to seed recommendations from existing Spotify
  listening history.
- Deployment notes for running the Streamlit app on a remote host (e.g. AWS
  EC2), including handling the OAuth redirect URI and running Ollama
  alongside it.