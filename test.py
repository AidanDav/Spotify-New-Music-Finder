from parsing import parse_selection

tracks = [
    {"name": "Night Light", "artist": "The Rions"},
    {"name": "Our Paradise", "artist": "The Terrys"},
    {"name": "Thrills", "artist": "Spacey Jane"},
]

display = [f"{t['name']} by {t['artist']}" for t in tracks]
targets = [t["name"] for t in tracks]

print("Displayed to user:")
for i, d in enumerate(display, 1):
    print(f"  {i}. {d}")

cases = [
    "1",
    "queue 2",
    "1 and 3",
    "Thrills",
    "thrills",
    "queue Our Paradise please",
    "Thrills by Spacey Jane",
    "Night Light and Thrills",
    "7",
    "",
    "the second one",
]

print("\nResults:")
for c in cases:
    indices, error = parse_selection(c, display, match_targets=targets)
    if error:
        print(f'  {c!r:32} -> ERROR: {error}')
    else:
        print(f'  {c!r:32} -> {[display[i] for i in indices]}')