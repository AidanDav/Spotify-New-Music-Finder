# Spotify-New-Music-Finder

To start:  source venv/Scripts/activate


Spotify-New-Music-Finder/
├── main.py                 # Entry point — runs the conversation loop, ties everything together
├── mistral_client.py        # extract_query(), format_results_with_mistral(), any other Mistral-calling functions
├── lastfm_client.py  (COMPLETED)        # get_similar_artists(), get_similar_songs() 
├── spotify_client.py  (COMPLETED)        # spotipy auth setup, search, queue, current_playback polling
├── database.py               # SQLite setup, add_liked(), add_blacklisted(), is_blacklisted(), etc.
├── config.py     (COMPLETED)             # API keys/secrets loaded from .env — never hardcoded here 
├── .env          (COMPLETED)              # Your actual keys (git-ignored, never committed) 
├── .gitignore    (COMPLETED)              # completed
├── requirements.txt
└── venv/         (COMPLETED)               # (git-ignored) -- completed (source file)