#!/bin/bash

# Add a song from Rhythm+ to the local repository
# Usage: ./scripts/add-song.sh <song-id>
#
# This script:
# 1. Fetches song metadata from the Rhythm+ API
# 2. Fetches all sheets (beatmaps) for the song
# 3. Downloads the video (240p for small file size)
# 4. Downloads the cover image
# 5. Creates the local directory structure
# 6. Updates songlist.json
#
# Authentication:
# Set RHYTHM_PLUS_TOKEN environment variable, or the script will try to get one automatically.
# To get a token manually:
#   1. Go to rhythm-plus.com
#   2. Open DevTools > Network
#   3. Find a request to api.rhythm-plus.com
#   4. Copy the Authorization header value (without "Bearer ")

set -e

SONG_ID="$1"
API_BASE="https://api.rhythm-plus.com/api/v1"
MAX_VIDEO_SIZE_MB=10  # Maximum allowed video size in MB
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
    echo ""
    echo "You can find song IDs by browsing rhythm-plus.com and looking at the URL"
    echo "or network requests when selecting a song."
    exit 1
fi

# Get auth token
get_firebase_token() {
    # Firebase API key from rhythm-plus.com
    API_KEY="AIzaSyAdeWHYbSj2iErECQTncQLrz9WdfbuiCsQ"

    # Sign in anonymously to Firebase
    RESPONSE=$(curl -s "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=$API_KEY" \
        -H "Content-Type: application/json" \
        --data-raw '{"returnSecureToken":true}')

    if [ -z "$RESPONSE" ]; then
        echo "ERROR: Empty response from Firebase" >&2
        return 1
    fi

    # Check for error in response
    ERROR=$(echo "$RESPONSE" | jq -r '.error.message // empty')
    if [ -n "$ERROR" ]; then
        echo "ERROR: Firebase auth failed: $ERROR" >&2
        return 1
    fi

    TOKEN=$(echo "$RESPONSE" | jq -r '.idToken // empty')
    if [ -z "$TOKEN" ]; then
        echo "ERROR: No idToken in response: $RESPONSE" >&2
        return 1
    fi
    echo "$TOKEN"
}

if [ -z "$RHYTHM_PLUS_TOKEN" ]; then
    echo -e "${GREEN}Getting auth token...${NC}"
    RHYTHM_PLUS_TOKEN=$(get_firebase_token)
    if [ $? -ne 0 ] || [ -z "$RHYTHM_PLUS_TOKEN" ]; then
        echo -e "${RED}Error: Could not get auth token automatically${NC}"
        echo "Please set RHYTHM_PLUS_TOKEN environment variable manually."
        echo "See script header for instructions."
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Got anonymous auth token"
fi

AUTH_HEADER="Authorization: Bearer $RHYTHM_PLUS_TOKEN"

# Check for required tools
for cmd in curl jq yt-dlp; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}Error: $cmd is required but not installed${NC}"
        exit 1
    fi
done

SONG_DIR="$SONGS_DIR/$SONG_ID"

# Check if song already exists
if [ -d "$SONG_DIR" ]; then
    echo -e "${YELLOW}Warning: Song directory already exists: $SONG_DIR${NC}"
    read -p "Do you want to overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    rm -rf "$SONG_DIR"
fi

echo -e "${GREEN}Fetching song metadata...${NC}"
SONG_DATA=$(curl -s -H "$AUTH_HEADER" "$API_BASE/song/get?songId=$SONG_ID")

if [ "$(echo "$SONG_DATA" | jq -r '.id // empty')" = "" ]; then
    echo -e "${RED}Error: Could not fetch song data. Response:${NC}"
    echo "$SONG_DATA"
    exit 1
fi

TITLE=$(echo "$SONG_DATA" | jq -r '.title')
ARTIST=$(echo "$SONG_DATA" | jq -r '.artist')
SRC_MODE=$(echo "$SONG_DATA" | jq -r '.srcMode')
SRC_REF=$(echo "$SONG_DATA" | jq -r '.srcRef')

echo -e "  Title: ${GREEN}$TITLE${NC}"
echo -e "  Artist: ${GREEN}$ARTIST${NC}"
echo -e "  Source: ${GREEN}$SRC_MODE${NC} ($SRC_REF)"

# Create song directory
mkdir -p "$SONG_DIR/sheets"

echo -e "${GREEN}Fetching sheet list...${NC}"
SHEETS_DATA=$(curl -s -H "$AUTH_HEADER" "$API_BASE/sheet/list?songId=$SONG_ID&visibilityLevel=public")

# Check if response is an array
if ! echo "$SHEETS_DATA" | jq -e 'type == "array"' > /dev/null 2>&1; then
    echo -e "${RED}Error: Unexpected sheet list response:${NC}"
    echo "$SHEETS_DATA"
    exit 1
fi

SHEET_COUNT=$(echo "$SHEETS_DATA" | jq 'length')
echo -e "  Found ${GREEN}$SHEET_COUNT${NC} sheets"

# Filter to only 4-key sheets
SHEETS_4KEY=$(echo "$SHEETS_DATA" | jq '[.[] | select(.keys == 4)]')
SHEET_COUNT_4KEY=$(echo "$SHEETS_4KEY" | jq 'length')

if [ "$SHEET_COUNT_4KEY" -eq 0 ]; then
    echo -e "${RED}Error: No 4-key sheets found for this song${NC}"
    echo -e "${RED}Removing song directory and aborting...${NC}"
    rm -rf "$SONG_DIR"
    exit 1
fi

echo -e "  Found ${GREEN}$SHEET_COUNT_4KEY${NC} 4-key sheets (filtered from $SHEET_COUNT total)"

# Save sheets.json (without mapping data - that goes in individual files)
echo "$SHEETS_4KEY" | jq '.' > "$SONG_DIR/sheets.json"

# Fetch each sheet with full mapping data
DIFFICULTIES=()
echo -e "${GREEN}Fetching sheet details...${NC}"
for SHEET_ID in $(echo "$SHEETS_4KEY" | jq -r '.[].id'); do
    SHEET_DATA=$(curl -s -H "$AUTH_HEADER" "$API_BASE/sheet/get?sheetId=$SHEET_ID")
    DIFFICULTY=$(echo "$SHEET_DATA" | jq -r '.difficulty')
    TITLE_SHEET=$(echo "$SHEET_DATA" | jq -r '.title')
    echo -e "  [$DIFFICULTY] $TITLE_SHEET"

    # Save individual sheet file with mapping
    echo "$SHEET_DATA" | jq '.' > "$SONG_DIR/sheets/$SHEET_ID.json"

    DIFFICULTIES+=($DIFFICULTY)
done

# Get unique sorted difficulties
DIFFICULTIES_JSON=$(printf '%s\n' "${DIFFICULTIES[@]}" | sort -n | uniq | jq -s '.')

# Download video
echo -e "${GREEN}Downloading video (240p)...${NC}"
if [ "$SRC_MODE" = "youtube" ]; then
    # Try 240p AV1 + low quality audio, fall back to best available small format
    yt-dlp -f "395+139/18/best[height<=360]" \
        --merge-output-format mp4 \
        -o "$SONG_DIR/video.mp4" \
        "https://www.youtube.com/watch?v=$SRC_REF" || {
        echo -e "${YELLOW}Warning: Could not download preferred format, trying fallback...${NC}"
        yt-dlp -f "best[height<=360]" \
            -o "$SONG_DIR/video.mp4" \
            "https://www.youtube.com/watch?v=$SRC_REF"
    }
else
    echo -e "${YELLOW}Warning: srcMode is '$SRC_MODE', not youtube. Skipping video download.${NC}"
    echo -e "${YELLOW}You may need to manually add the video file.${NC}"
fi

# Check video file size
if [ -f "$SONG_DIR/video.mp4" ]; then
    VIDEO_SIZE_BYTES=$(stat -f%z "$SONG_DIR/video.mp4" 2>/dev/null || stat -c%s "$SONG_DIR/video.mp4" 2>/dev/null)
    VIDEO_SIZE_MB=$((VIDEO_SIZE_BYTES / 1024 / 1024))
    if [ "$VIDEO_SIZE_MB" -gt "$MAX_VIDEO_SIZE_MB" ]; then
        echo -e "${RED}Error: Video file is too large (${VIDEO_SIZE_MB}MB > ${MAX_VIDEO_SIZE_MB}MB limit)${NC}"
        echo -e "${RED}Removing song directory and aborting...${NC}"
        rm -rf "$SONG_DIR"
        exit 1
    fi
fi

# Download cover image
echo -e "${GREEN}Downloading cover image...${NC}"
IMAGE_URL=$(echo "$SONG_DATA" | jq -r '.image')
if [ "$IMAGE_URL" = "null" ] || [ -z "$IMAGE_URL" ]; then
    # Use YouTube thumbnail as fallback
    IMAGE_URL="https://img.youtube.com/vi/$SRC_REF/mqdefault.jpg"
fi
curl -s -o "$SONG_DIR/cover.jpg" "$IMAGE_URL"

# Update songlist.json
echo -e "${GREEN}Updating songlist.json...${NC}"

# Build the new song entry
NEW_SONG=$(cat <<EOF
{
  "id": "$SONG_ID",
  "title": $(echo "$SONG_DATA" | jq '.title'),
  "subtitle": $(echo "$SONG_DATA" | jq '.subtitle // ""'),
  "artist": $(echo "$SONG_DATA" | jq '.artist'),
  "image": "/songs/$SONG_ID/cover.jpg",
  "difficulties": $DIFFICULTIES_JSON,
  "keys": [4],
  "srcMode": "video",
  "srcRef": "/songs/$SONG_ID/video.mp4",
  "verified": $(echo "$SONG_DATA" | jq '.verified // false'),
  "tags": $(echo "$SONG_DATA" | jq '.tags // []')
}
EOF
)

# Check if song already in songlist
if jq -e ".[] | select(.id == \"$SONG_ID\")" "$SONGLIST_FILE" > /dev/null 2>&1; then
    # Update existing entry
    jq "map(if .id == \"$SONG_ID\" then $NEW_SONG else . end)" "$SONGLIST_FILE" > "$SONGLIST_FILE.tmp"
else
    # Add new entry
    jq ". + [$NEW_SONG]" "$SONGLIST_FILE" > "$SONGLIST_FILE.tmp"
fi
mv "$SONGLIST_FILE.tmp" "$SONGLIST_FILE"

# Show summary
VIDEO_SIZE=$(du -h "$SONG_DIR/video.mp4" 2>/dev/null | cut -f1 || echo "N/A")
echo ""
echo -e "${GREEN}✓ Song added successfully!${NC}"
echo -e "  Directory: $SONG_DIR"
echo -e "  Video size: $VIDEO_SIZE"
echo -e "  Sheets: $SHEET_COUNT"
echo -e "  Difficulties: $(echo $DIFFICULTIES_JSON | jq -r 'join(", ")')"
