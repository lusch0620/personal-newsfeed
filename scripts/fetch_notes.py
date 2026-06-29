"""
fetch_notes.py
Reads user notes from the Gist sync file and writes data/notes.md.
Notes older than 3 months are archived to data/notes_archive/YYYY-MM.md.
Runs in CI before summarize.py so notes are available as scoring context.
"""

import json
import os
import urllib.request
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT         = Path(__file__).parent.parent
NOTES_PATH   = ROOT / "data" / "notes.md"
ARCHIVE_DIR  = ROOT / "data" / "notes_archive"
GIST_ID      = "8a4b09f2ceb018c3b45460ee40e1ced9"
SYNC_FILE    = "newsfeed-sync.json"
MAX_NOTES    = 30   # cap context length fed to Haiku
ARCHIVE_DAYS = 90   # notes older than this get archived
MIN_ARCHIVE_LEN = 20  # notes shorter than this are dropped rather than archived


def fetch_gist(pat: str) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def format_note_block(note: dict) -> list[str]:
    ts       = note.get("ts", 0)
    date_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    title    = note.get("title", "").strip()
    src      = note.get("src", "").strip()
    text     = note.get("text", "").strip()
    lines = []
    if title:
        lines.append(f"### {date_str} — {title}")
        if src:
            lines.append(f"**Source:** {src}")
    else:
        lines.append(f"### {date_str}")
    lines.append(f"> {text}")
    lines.append("")
    return lines


def write_notes_md(recent: list[dict], updated: str) -> int:
    lines = [
        "# Research Notes",
        "*Personal annotations from the newsfeed. Injected into scoring context each pipeline run.*",
        f"*Last updated: {updated}*",
        "",
        "---",
        "",
    ]
    written = 0
    for note in recent[:MAX_NOTES]:
        if not note.get("text", "").strip():
            continue
        lines.extend(format_note_block(note))
        written += 1
    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(NOTES_PATH, "w") as f:
        f.write("\n".join(lines))
    return written


def write_archive(old: list[dict]) -> int:
    by_month: dict[str, list[dict]] = defaultdict(list)
    for note in old:
        text = note.get("text", "").strip()
        if len(text) < MIN_ARCHIVE_LEN:
            continue  # drop thin notes rather than archiving
        ts = note.get("ts", 0)
        month_key = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")
        by_month[month_key].append(note)

    archived = 0
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for month_key, month_notes in sorted(by_month.items()):
        path = ARCHIVE_DIR / f"{month_key}.md"
        lines = [
            f"# Research Notes Archive — {month_key}",
            "*Auto-archived from newsfeed annotations.*",
            "",
            "---",
            "",
        ]
        for note in sorted(month_notes, key=lambda n: n.get("ts", 0), reverse=True):
            lines.extend(format_note_block(note))
            archived += 1
        with open(path, "w") as f:
            f.write("\n".join(lines))
    return archived


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

    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=ARCHIVE_DAYS)).timestamp() * 1000
    all_notes = sorted(notes.values(), key=lambda n: n.get("ts", 0), reverse=True)
    recent = [n for n in all_notes if n.get("ts", 0) >= cutoff_ts]
    old    = [n for n in all_notes if n.get("ts", 0) <  cutoff_ts]

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    written  = write_notes_md(recent, updated)
    archived = write_archive(old)

    print(f"notes.md: {written} recent notes")
    if archived:
        print(f"Archived {archived} notes older than {ARCHIVE_DAYS} days to {ARCHIVE_DIR}")


if __name__ == "__main__":
    main()
