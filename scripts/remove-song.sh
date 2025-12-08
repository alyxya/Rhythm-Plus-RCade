#!/bin/bash

# Remove a song from the local repository
# Usage: ./scripts/remove-song.sh <song-id>

set -e

SONG_ID="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SONGS_DIR="$SCRIPT_DIR/../public/songs"
SONGLIST_FILE="$SONGS_DIR/songlist.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ -z "$SONG_ID" ]; then
    echo -e "${RED}Error: Please provide a song ID${NC}"
    echo "Usage: $0 <song-id>"
    exit 1
fi

SONG_DIR="$SONGS_DIR/$SONG_ID"

# Check if song exists
if [ ! -d "$SONG_DIR" ]; then
    echo -e "${RED}Error: Song directory not found: $SONG_DIR${NC}"
    exit 1
fi

# Get song title for confirmation
TITLE=$(jq -r ".[] | select(.id == \"$SONG_ID\") | .title" "$SONGLIST_FILE" 2>/dev/null || echo "Unknown")
ARTIST=$(jq -r ".[] | select(.id == \"$SONG_ID\") | .artist" "$SONGLIST_FILE" 2>/dev/null || echo "Unknown")

echo -e "Song to remove:"
echo -e "  ID: ${YELLOW}$SONG_ID${NC}"
echo -e "  Title: ${YELLOW}$TITLE${NC}"
echo -e "  Artist: ${YELLOW}$ARTIST${NC}"
echo ""

read -p "Are you sure you want to remove this song? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Aborted.${NC}"
    exit 0
fi

# Remove from songlist.json
echo -e "${GREEN}Removing from songlist.json...${NC}"
jq "[.[] | select(.id != \"$SONG_ID\")]" "$SONGLIST_FILE" > "$SONGLIST_FILE.tmp"
mv "$SONGLIST_FILE.tmp" "$SONGLIST_FILE"

# Remove song directory
echo -e "${GREEN}Removing song directory...${NC}"
rm -rf "$SONG_DIR"

echo ""
echo -e "${GREEN}✓ Song removed successfully!${NC}"
