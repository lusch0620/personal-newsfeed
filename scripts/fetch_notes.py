"""
fetch_notes.py
Reads user notes from the Gist sync file and writes data/notes.md.
Runs in CI before summarize.py so notes are available as scoring context.
"""

import json
import os
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT       = Path(__file__).parent.parent
NOTES_PATH = ROOT / "data" / "notes.md"
GIST_ID    = "be1fddb5fb8215040ef67d3d79253301"
SYNC_FILE  = "newsfeed-sync.json"
MAX_NOTES  = 30  # cap context length fed to Haiku


def fetch_gist(pat: str) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def main():
    pat = os.environ.get("SYNC_GIST_PAT", "").strip()
    if not pat:
        print("SYNC_GIST_PAT not set — skipping notes fetch")
        return

    try:
        gist = fetch_gist(pat)
    except Exception as e:
        print(f"Failed to fetch Gist: {e}")
        return

    raw = gist.get("files", {}).get(SYNC_FILE, {}).get("content", "{}")
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        print("Failed to parse Gist content")
        return

    notes = state.get("notes", {})
    if not notes:
        print("No notes in Gist — skipping notes.md write")
        return

    # Sort newest first, cap at MAX_NOTES
    sorted_notes = sorted(notes.values(), key=lambda n: n.get("ts", 0), reverse=True)[:MAX_NOTES]

    lines = [
        "# Research Notes",
        "*Personal annotations from the newsfeed. Injected into scoring context each pipeline run.*",
        f"*Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        "---",
        "",
    ]

    for note in sorted_notes:
        ts       = note.get("ts", 0)
        date_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        title    = note.get("title", "").strip()
        src      = note.get("src", "").strip()
        text     = note.get("text", "").strip()
        if not text:
            continue

        if title:
            lines.append(f"### {date_str} — {title}")
            if src:
                lines.append(f"**Source:** {src}")
        else:
            lines.append(f"### {date_str}")

        lines.append(f"> {text}")
        lines.append("")

    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(NOTES_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"Wrote {len(sorted_notes)} notes to {NOTES_PATH}")


if __name__ == "__main__":
    main()
