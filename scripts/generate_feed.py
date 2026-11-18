#!/usr/bin/env python3
"""Generate feed.xml from manifest.json + audio/*.mp3.

Run after any change to manifest.json or audio/. itunes:type is "serial" so
Apple Podcasts (and most apps) default to oldest-first playback -- the whole
point of this feed is a stable listening order across daily/fde/on-demand
episodes, not the usual newest-first podcast convention.
"""
import json
import os
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

try:
    from mutagen.mp3 import MP3
except ImportError:  # duration is optional -- feed still valid without it
    MP3 = None

REPO_OWNER = "cwinter1"
REPO_NAME = "audio-personal"
# raw.githubusercontent.com serves .xml as text/plain with X-Content-Type-Options:
# nosniff, which made Apple Podcasts refuse the feed outright (attempt 1). jsDelivr's
# GitHub CDN mirror fixed that but Apple still couldn't subscribe (attempt 2).
# GitHub Pages fixed feed.xml's content-type too, but its mime map serves .mp3 as
# "audio/mp3" (non-standard) while the feed declares enclosures as "audio/mpeg"
# (the real IANA type) -- that mismatch, present on every single episode, is a
# concrete, verifiable inconsistency a strict parser could reject on. jsDelivr
# serves .mp3 correctly as "audio/mpeg", so: feed.xml + artwork from Pages
# (correct application/xml, image/png), audio enclosures from jsDelivr (correct
# audio/mpeg) -- each host for what it actually serves right.
PAGES_BASE = f"https://{REPO_OWNER}.github.io/{REPO_NAME}"
JSDELIVR_BASE = f"https://cdn.jsdelivr.net/gh/{REPO_OWNER}/{REPO_NAME}@main"
FEED_URL = f"{PAGES_BASE}/feed.xml"
RAW_BASE = PAGES_BASE
AUDIO_BASE = JSDELIVR_BASE

SOURCE_LABELS = {
    "daily": "Daily",
    "fde": "FDE",
    "on-demand": "On-Demand",
}


def load_manifest(path="manifest.json"):
    with open(path) as f:
        return json.load(f)


def get_duration_seconds(entry, audio_path):
    """Duration for itunes:duration. Prefer the value news recorded at sync
    time; fall back to reading the MP3 header so the episodes imported before
    that field existed still get one. None means unknown (tag is omitted)."""
    recorded = entry.get("duration_seconds")
    if recorded:
        return float(recorded)
    if MP3 is None:
        return None
    try:
        return float(MP3(audio_path).info.length)
    except Exception as e:
        print(f"WARNING: cannot read duration of {audio_path}: {e}", file=sys.stderr)
        return None


def format_duration(seconds):
    total = int(round(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def cdata(text):
    """Wrap text in CDATA, splitting any literal ']]>' so it can't end the section early."""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def build_show_notes(entry, label):
    """(plain, html) show notes. Falls back to the old one-line description
    for manifest entries that have no description."""
    base = entry.get("description") or f"{entry['title']} ({label}, {entry['date']})"
    link = entry.get("link")
    plain = base
    html = "".join(f"<p>{escape(p)}</p>" for p in base.split("\n\n") if p.strip())
    if link:
        plain += f"\n\nSource: {link}"
        html += f'<p><a href="{escape(link)}">Source</a></p>'
    return plain, html


def build_item(entry, episode_number):
    filename = entry["filename"]
    audio_path = os.path.join("audio", filename)
    if not os.path.exists(audio_path):
        print(f"WARNING: {audio_path} listed in manifest but missing on disk, skipping", file=sys.stderr)
        return None
    # Measured from the file in this checkout, not trusted from the manifest:
    # Apple expects enclosure length to be the real byte count.
    size = os.path.getsize(audio_path)
    label = SOURCE_LABELS.get(entry["source"], entry["source"])
    title = f"[{label}] {entry['title']}"
    # Stagger pubDate by source within a day so items on the same date still
    # get a stable, distinct order in apps that ignore itunes:episode.
    hour = {"daily": 4, "fde": 5, "on-demand": 12}.get(entry["source"], 12)
    pub_dt = datetime.strptime(entry["date"], "%Y-%m-%d").replace(
        hour=hour, tzinfo=timezone.utc
    )
    enclosure_url = f"{AUDIO_BASE}/audio/{filename}"
    guid = filename
    plain_notes, html_notes = build_show_notes(entry, label)
    item_link = entry.get("link") or f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
    duration = get_duration_seconds(entry, audio_path)
    duration_tag = (
        f"\n      <itunes:duration>{format_duration(duration)}</itunes:duration>"
        if duration else ""
    )
    # No itunes:season on purpose: with itunes:type "serial", Apple sorts by
    # season first, which would split the one cross-source listening order
    # (daily/fde/on-demand) this feed exists to provide into per-source blocks.
    return f"""    <item>
      <title>{escape(title)}</title>
      <itunes:title>{escape(entry['title'])}</itunes:title>
      <link>{escape(item_link)}</link>
      <guid isPermaLink="false">{escape(guid)}</guid>
      <pubDate>{format_datetime(pub_dt)}</pubDate>
      <itunes:episode>{episode_number}</itunes:episode>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>{duration_tag}
      <enclosure url="{escape(enclosure_url)}" length="{size}" type="audio/mpeg" />
      <description>{escape(plain_notes)}</description>
      <itunes:summary>{escape(plain_notes)}</itunes:summary>
      <content:encoded>{cdata(html_notes)}</content:encoded>
    </item>"""


def generate_feed(manifest, out_path="feed.xml"):
    manifest_sorted = sorted(manifest, key=lambda e: (e["date"], e["source"]))
    items = []
    for i, entry in enumerate(manifest_sorted, start=1):
        item_xml = build_item(entry, i)
        if item_xml:
            items.append(item_xml)

    now = format_datetime(datetime.now(timezone.utc))
    channel_link = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
    image_url = f"{RAW_BASE}/artwork.png"

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml" />
    <title>AI Daily Brief — Personal Audio Archive</title>
    <link>{channel_link}</link>
    <description>Personal archive of daily/FDE/on-demand AI Daily Brief episodes, in listening order.</description>
    <language>en-us</language>
    <copyright>Personal use</copyright>
    <itunes:subtitle>Daily, FDE and on-demand briefs in listening order</itunes:subtitle>
    <itunes:summary>Personal archive of daily/FDE/on-demand AI Daily Brief episodes, in listening order.</itunes:summary>
    <itunes:type>serial</itunes:type>
    <itunes:explicit>false</itunes:explicit>
    <itunes:author>Chris Winter</itunes:author>
    <itunes:owner>
      <itunes:name>Chris Winter</itunes:name>
      <itunes:email>new.chriswinter@gmail.com</itunes:email>
    </itunes:owner>
    <itunes:category text="Technology" />
    <itunes:image href="{image_url}" />
    <image>
      <url>{image_url}</url>
      <title>AI Daily Brief — Personal Audio Archive</title>
      <link>{channel_link}</link>
    </image>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>
"""
    with open(out_path, "w") as f:
        f.write(feed)
    print(f"Wrote {out_path} with {len(items)} episodes")


if __name__ == "__main__":
    generate_feed(load_manifest())
