#!/usr/bin/env python3
"""
Add songs from SONGS_TO_ADD.md using the Rhythm+ API.

Usage:
    python3 batch_add_songs.py           # Add the next song in the list
    python3 batch_add_songs.py 5         # Add the next 5 songs
    python3 batch_add_songs.py --status  # Show progress status
    python3 batch_add_songs.py --reset   # Reset progress (start over)
    python3 batch_add_songs.py --search-only -o candidates.json --top 5  # Only search, do not download
    python3 batch_add_songs.py --download-from candidates.json           # Download using approved candidates

For each song:
1. Search the API for matching songs
2. Pick the most popular result (by playCount, with list order as tiebreaker)
3. Add the song using add-song.sh
4. If it fails (too large, no valid tracks, etc.), try the next most popular result
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

API_BASE = "https://api.rhythm-plus.com/api/v1"
FIREBASE_API_KEY = "AIzaSyAdeWHYbSj2iErECQTncQLrz9WdfbuiCsQ"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ADD_SONG_SCRIPT = os.path.join(SCRIPT_DIR, "add-song.sh")
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PROGRESS_FILE = os.path.join(PROJECT_ROOT, ".song_progress.json")
CANDIDATES_FILE_DEFAULT = os.path.join(PROJECT_ROOT, ".song_candidates.json")


def get_firebase_token():
    """Get an anonymous Firebase auth token."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    data = json.dumps({"returnSecureToken": True}).encode('utf-8')

    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('idToken')
    except urllib.error.HTTPError as e:
        print(f"Error getting Firebase token: {e}")
        return None


def search_songs(query, token):
    """Search for songs matching the query."""
    encoded_query = urllib.parse.quote(query)
    url = f"{API_BASE}/song/list?visibilityLevel=public&orderBy=updated_at&limit=100&order=desc&searchTerm={encoded_query}&difficulty=&key="

    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"  Error searching for '{query}': {e}")
        return []


def extract_song_info(line):
    """Extract song title and artist from a markdown line."""
    # Format: "- Song Title — Artist (description)"
    # or: "- Song Title — Artist"
    match = re.match(r'^- (.+?) — (.+?)(?:\s*\(|$)', line)
    if match:
        title = match.group(1).strip()
        artist = match.group(2).strip()
        return title, artist

    # Format: "- Song Title - Artist (description)" (with regular dash)
    match = re.match(r'^- (.+?) - (.+?)(?:\s*\(|$)', line)
    if match:
        title = match.group(1).strip()
        artist = match.group(2).strip()
        return title, artist

    return None, None


def add_song(song_id, token):
    """Add a song using the add-song.sh script. Returns True on success."""
    env = os.environ.copy()
    env['RHYTHM_PLUS_TOKEN'] = token

    try:
        result = subprocess.run(
            [ADD_SONG_SCRIPT, song_id],
            env=env,
            capture_output=True,
            text=True,
            input='y\n'  # Auto-confirm overwrite if song exists
        )

        if result.returncode == 0:
            return True, None
        else:
            error_msg = result.stderr or result.stdout
            return False, error_msg
    except Exception as e:
        return False, str(e)


def normalize_for_comparison(s):
    """Normalize a string for comparison - lowercase, remove punctuation/extra spaces."""
    s = s.lower()
    s = re.sub(r'[^\w\s]', '', s)  # Remove punctuation
    s = re.sub(r'\s+', ' ', s).strip()  # Normalize whitespace
    return s


def title_matches(search_title, result_title):
    """Check if the search title appears in the result title (normalized)."""
    search_norm = normalize_for_comparison(search_title)
    result_norm = normalize_for_comparison(result_title)

    # Check if search title is contained in result title or vice versa
    return search_norm in result_norm or result_norm in search_norm


def get_search_queries(title, artist):
    """Generate search queries to try, in order of preference."""
    queries = []

    # Clean up title and artist
    title_clean = re.sub(r'\s*\([^)]*\)\s*', ' ', title).strip()  # Remove parentheticals
    title_clean = re.sub(r'\s+', ' ', title_clean)  # Normalize whitespace

    artist_clean = artist.split('/')[0].strip()  # Take first artist if multiple
    artist_clean = re.sub(r'\s*ft\.?\s*.+$', '', artist_clean, flags=re.IGNORECASE)  # Remove "ft. X"
    artist_clean = re.sub(r'\s*x\s+.+$', '', artist_clean, flags=re.IGNORECASE)  # Remove "x Artist"

    # Remove special characters for simpler searches
    title_simple = re.sub(r'[^\w\s]', '', title_clean).strip()
    title_simple = re.sub(r'\s+', ' ', title_simple)

    artist_simple = re.sub(r'[^\w\s]', '', artist_clean).strip()

    # Get first word of title (for very loose matching)
    title_first_word = title_simple.split()[0] if title_simple.split() else title_simple

    # Try various combinations from most specific to loosest
    queries.append(title_clean)  # Just title (clean) - often best for unique titles
    queries.append(f"{title_clean} {artist_clean}")  # Title + artist
    queries.append(title_simple)  # Title without special chars
    queries.append(f"{title_simple} {artist_simple}")  # Both simplified
    queries.append(artist_clean)  # Just artist (might find other songs by same artist)

    # For titles with numbers/punctuation that might be stripped differently
    if title_simple != title_clean:
        queries.append(title_simple)

    # Very loose: first significant word of title
    if len(title_first_word) > 3:
        queries.append(title_first_word)

    # Remove duplicates while preserving order
    seen = set()
    unique_queries = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            unique_queries.append(q)

    return unique_queries


def collect_candidates(title, artist, token, top_n=5):
    """Search and return up to top_n candidate results."""
    queries = get_search_queries(title, artist)
    all_results = []
    used_query = None

    for query in queries:
        results = search_songs(query, token)
        if results:
            used_query = query
            for idx, result in enumerate(results):
                if not any(r['id'] == result['id'] for r, _ in all_results):
                    all_results.append((result, idx))
            if all_results:
                break

    if not all_results:
        return [], used_query

    title_clean = re.sub(r'\s*\([^)]*\)\s*', ' ', title).strip()
    title_clean = re.sub(r'\s+', ' ', title_clean)

    matching_results = [
        (r, idx) for r, idx in all_results
        if title_matches(title_clean, r.get('title', ''))
    ]

    if not matching_results:
        return [], used_query

    def sort_key(item):
        result, idx = item
        popularity = result.get('popularityScore', 0) or 0
        return (-popularity, idx)

    matching_results.sort(key=sort_key)
    trimmed = matching_results[:top_n]

    candidates = []
    for result, _ in trimmed:
        candidates.append({
            "id": result.get('id'),
            "title": result.get('title'),
            "artist": result.get('artist'),
            "popularityScore": result.get('popularityScore', 0),
            "matchedQuery": used_query,
        })

    return candidates, used_query


def load_progress():
    """Load progress from file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"processed": [], "added": [], "failed": [], "skipped": []}


def save_progress(progress):
    """Save progress to file."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def load_songs(song_file=None):
    """Load songs from the song list (supports bullets or numbered lists)."""
    if not song_file:
        song_file = os.path.join(PROJECT_ROOT, "SONGS_TO_ADD.md")
        if not os.path.exists(song_file):
            song_file = None

    if not song_file:
        print("Error: No song list found (expected SONGS_TO_ADD.md).")
        sys.exit(1)

    with open(song_file, 'r') as f:
        lines = f.readlines()

    songs = []
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith('#'):
            continue

        # Accept "- Title — Artist" or "1. Title — Artist" formats
        if raw.startswith('- '):
            canonical = raw
        else:
            num_match = re.match(r'^\d+\.\s+(.*)$', raw)
            if num_match:
                canonical = f"- {num_match.group(1).strip()}"
            else:
                continue

        title, artist = extract_song_info(canonical)
        if title and artist:
            songs.append((title, artist, canonical))
    return songs


def show_status():
    """Show current progress status."""
    progress = load_progress()
    songs = load_songs()

    processed_set = set(progress["processed"])
    remaining = [s for s in songs if s[2] not in processed_set]

    print(f"Total songs:   {len(songs)}")
    print(f"Added:         {len(progress['added'])}")
    print(f"Failed:        {len(progress['failed'])}")
    print(f"Skipped:       {len(progress['skipped'])}")
    print(f"Remaining:     {len(remaining)}")
    print()

    if remaining:
        print("Next up:")
        for title, artist, _ in remaining[:5]:
            print(f"  - {title} — {artist}")
        if len(remaining) > 5:
            print(f"  ... and {len(remaining) - 5} more")


def reset_progress():
    """Reset progress file."""
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("Progress reset.")
    else:
        print("No progress file to reset.")


def process_song(title, artist, original_line, token, progress, dry_run=False):
    """Process a single song. Returns True if added successfully."""
    print(f"Processing: {title} — {artist}")

    # Try different search queries
    queries = get_search_queries(title, artist)
    all_results = []

    for query in queries:
        results = search_songs(query, token)
        if results:
            # Add results with their original index for tiebreaking
            for idx, result in enumerate(results):
                # Check if we already have this song ID
                if not any(r['id'] == result['id'] for r, _ in all_results):
                    all_results.append((result, idx))

            if all_results:
                break  # Found results, stop trying queries

    if not all_results:
        print(f"  No results found")
        progress["skipped"].append({"title": title, "artist": artist, "reason": "No results found"})
        progress["processed"].append(original_line)
        save_progress(progress)
        return False

    # Filter to only results where the title matches
    # Get the clean title for matching (without parentheticals)
    title_clean = re.sub(r'\s*\([^)]*\)\s*', ' ', title).strip()
    title_clean = re.sub(r'\s+', ' ', title_clean)

    matching_results = [
        (r, idx) for r, idx in all_results
        if title_matches(title_clean, r.get('title', ''))
    ]

    if not matching_results:
        print(f"  Found {len(all_results)} results but none matched title '{title_clean}'")
        progress["skipped"].append({"title": title, "artist": artist, "reason": "No title match"})
        progress["processed"].append(original_line)
        save_progress(progress)
        return False

    # Sort by popularityScore (descending), then by original list position (ascending)
    def sort_key(item):
        result, idx = item
        popularity = result.get('popularityScore', 0) or 0
        return (-popularity, idx)

    matching_results.sort(key=sort_key)

    print(f"  Found {len(matching_results)} matching results (from {len(all_results)} total)")

    # Try each result until one succeeds
    for result, _ in matching_results:
        song_id = result['id']
        popularity = result.get('popularityScore', 0)
        result_title = result.get('title', 'Unknown')
        result_artist = result.get('artist', 'Unknown')

        print(f"  Trying: {result_title} by {result_artist} (popularity: {popularity}, id: {song_id})")

        if dry_run:
            print(f"  [DRY RUN] Would attempt to add this song")
            return True

        ok, error = add_song(song_id, token)
        if ok:
            print(f"  ✓ Added successfully!")
            progress["added"].append({"title": title, "artist": artist, "song_id": song_id})
            progress["processed"].append(original_line)
            # Remove from skipped if it was there
            progress["skipped"] = [s for s in progress["skipped"] if s.get("title") != title]
            save_progress(progress)
            return True
        else:
            error_preview = error[:100] if error else 'Unknown error'
            print(f"  ✗ Failed: {error_preview}...")

    print(f"  ✗ All candidates failed")
    progress["failed"].append({"title": title, "artist": artist, "reason": "All candidates failed"})
    progress["processed"].append(original_line)
    save_progress(progress)
    return False


def process_selected_song(song_id, title, artist, original_line, token, progress):
    """Add a song using a pre-approved song ID."""
    print(f"Processing: {title} — {artist} (id: {song_id})")

    ok, error = add_song(song_id, token)
    if ok:
        print("  ✓ Added successfully!")
        progress["added"].append({"title": title, "artist": artist, "song_id": song_id})
        progress["processed"].append(original_line)
        progress["skipped"] = [s for s in progress["skipped"] if s.get("title") != title]
        save_progress(progress)
        return True

    error_preview = error[:100] if error else 'Unknown error'
    print(f"  ✗ Failed: {error_preview}...")
    progress["failed"].append({"title": title, "artist": artist, "reason": f"Failed with id {song_id}"})
    progress["processed"].append(original_line)
    save_progress(progress)
    return False


def preview_searches(count=5):
    """Show what search queries would be tried for upcoming songs."""
    songs = load_songs()
    progress = load_progress()

    processed_set = set(progress["processed"])
    remaining = [(t, a, l) for t, a, l in songs if l not in processed_set]

    for title, artist, _ in remaining[:count]:
        print(f"{title} — {artist}")
        queries = get_search_queries(title, artist)
        for i, q in enumerate(queries, 1):
            print(f"  {i}. \"{q}\"")
        print()


def main():
    parser = argparse.ArgumentParser(description="Add songs from SONGS_TO_ADD.md")
    parser.add_argument('count', nargs='?', type=int, default=1,
                        help='Number of songs to add (default: 1)')
    parser.add_argument('--status', action='store_true',
                        help='Show current progress status')
    parser.add_argument('--reset', action='store_true',
                        help='Reset progress and start over')
    parser.add_argument('--preview', type=int, nargs='?', const=5, metavar='N',
                        help='Preview search queries for next N songs (default: 5)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Search API but don\'t actually add songs')
    parser.add_argument('--search-only', action='store_true',
                        help='Search and save candidates without downloading')
    parser.add_argument('--download-from', metavar='FILE',
                        help='Download using selectedId values from a candidates file created with --search-only')
    parser.add_argument('--mark-unselected-skipped', action='store_true',
                        help='When using --download-from, mark entries without selectedId as skipped in progress')
    parser.add_argument('--output', '-o', default=CANDIDATES_FILE_DEFAULT,
                        help='Output file for --search-only (default: .song_candidates.json)')
    parser.add_argument('--top', type=int, default=5,
                        help='Number of candidates to save per song in --search-only (default: 5)')

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.reset:
        reset_progress()
        return

    if args.preview is not None:
        preview_searches(args.preview)
        return

    if args.search_only and args.download_from:
        print("Error: Choose either --search-only or --download-from, not both.")
        sys.exit(1)

    # Load songs and progress
    songs = load_songs()
    progress = load_progress()

    # Find remaining songs
    processed_set = set(progress["processed"])
    remaining = [(t, a, l) for t, a, l in songs if l not in processed_set]

    if args.search_only:
        if not remaining:
            print("All songs have been processed!")
            show_status()
            return

        to_process = remaining[:args.count]

        print(f"Searching for {len(to_process)} song(s)...")
        print(f"({len(remaining)} remaining total)")
        print()

        print("Getting Firebase auth token...")
        token = get_firebase_token()
        if not token:
            print("Error: Could not get auth token")
            sys.exit(1)
        print("Got auth token")
        print()

        collected = []
        for title, artist, original_line in to_process:
            print(f"Searching candidates for: {title} — {artist}")
            candidates, used_query = collect_candidates(title, artist, token, top_n=args.top)
            collected.append({
                "title": title,
                "artist": artist,
                "original_line": original_line,
                "candidates": candidates,
                "selectedId": None,
                "matchedQuery": used_query,
            })
            if not candidates:
                print("  No matching candidates found.")
            else:
                for idx, cand in enumerate(candidates, 1):
                    print(f"  {idx}. {cand.get('title')} — {cand.get('artist')} (id: {cand.get('id')}, popularity: {cand.get('popularityScore')})")
            print()

        with open(args.output, 'w') as f:
            json.dump(collected, f, indent=2)

        print(f"Saved candidates to {args.output}")
        print("Edit the file to set \"selectedId\" for each song, then run:")
        print(f"  python3 batch_add_songs.py --download-from {args.output}")
        return

    if args.download_from:
        try:
            with open(args.download_from, 'r') as f:
                candidates_data = json.load(f)
        except Exception as e:
            print(f"Error: Could not read candidates file: {e}")
            sys.exit(1)

        print(f"Downloading from candidates file: {args.download_from}")
        print()

        print("Getting Firebase auth token...")
        token = get_firebase_token()
        if not token:
            print("Error: Could not get auth token")
            sys.exit(1)
        print("Got auth token")
        print()

        added_any = False
        for entry in candidates_data:
            title = entry.get("title", "Unknown Title")
            artist = entry.get("artist", "Unknown Artist")
            original_line = entry.get("original_line") or entry.get("originalLine") or f"- {title} — {artist}"
            selected_id = entry.get("selectedId")

            if original_line in processed_set:
                print(f"Skipping {title} — {artist}: already processed.")
                continue

            if not selected_id:
                if args.mark_unselected_skipped:
                    print(f"Skipping {title} — {artist}: no selectedId set (marking as skipped).")
                    # Remove any previous skip entry for this title
                    progress["skipped"] = [s for s in progress["skipped"] if s.get("title") != title]
                    progress["skipped"].append({"title": title, "artist": artist, "reason": "No selectedId in candidates"})
                    progress["processed"].append(original_line)
                    processed_set.add(original_line)
                    save_progress(progress)
                else:
                    print(f"Skipping {title} — {artist}: no selectedId set.")
                continue

            process_selected_song(selected_id, title, artist, original_line, token, progress)
            added_any = True
            print()

        if not added_any:
            print("No songs were added. Set selectedId in the candidates file and try again.")
            return

        print("=" * 60)
        show_status()
        return

    if not remaining:
        print("All songs have been processed!")
        show_status()
        return

    # Limit to requested count
    to_process = remaining[:args.count]

    print(f"Processing {len(to_process)} song(s)...")
    print(f"({len(remaining)} remaining total)")
    print()

    # Get auth token
    print("Getting Firebase auth token...")
    token = get_firebase_token()
    if not token:
        print("Error: Could not get auth token")
        sys.exit(1)
    print("Got auth token")
    print()

    # Process songs
    for i, (title, artist, original_line) in enumerate(to_process):
        print(f"[{i+1}/{len(to_process)}] ", end="")
        process_song(title, artist, original_line, token, progress, dry_run=args.dry_run)
        print()

    # Show summary
    print("=" * 60)
    show_status()


if __name__ == '__main__':
    main()
