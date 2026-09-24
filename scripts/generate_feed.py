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

REPO_OWNER = "cwinter1"
REPO_NAME = "audio-personal"
# raw.githubusercontent.com serves .xml as text/plain with X-Content-Type-Options:
# nosniff, which made Apple Podcasts refuse the feed outright (attempt 1). jsDelivr's
# GitHub CDN mirror fixed content-type but Apple's crawler still couldn't subscribe
# (attempt 2) -- CDN bot-detection/WAF friction is the leading suspect, though never
# confirmed since Apple gives no detail. GitHub Pages (attempt 3) is the standard,
# widely-used host for exactly this pattern and has no history of that kind of
# crawler friction.
PAGES_BASE = f"https://{REPO_OWNER}.github.io/{REPO_NAME}"
FEED_URL = f"{PAGES_BASE}/feed.xml"
RAW_BASE = PAGES_BASE

SOURCE_LABELS = {
    "daily": "Daily",
    "fde": "FDE",
    "on-demand": "On-Demand",
}


def load_manifest(path="manifest.json"):
    with open(path) as f:
        return json.load(f)


def build_item(entry, episode_number):
    filename = entry["filename"]
    audio_path = os.path.join("audio", filename)
    if not os.path.exists(audio_path):
        print(f"WARNING: {audio_path} listed in manifest but missing on disk, skipping", file=sys.stderr)
        return None
    size = os.path.getsize(audio_path)
    label = SOURCE_LABELS.get(entry["source"], entry["source"])
    title = f"[{label}] {entry['title']}"
    # Stagger pubDate by source within a day so items on the same date still
    # get a stable, distinct order in apps that ignore itunes:episode.
    hour = {"daily": 4, "fde": 5, "on-demand": 12}.get(entry["source"], 12)
    pub_dt = datetime.strptime(entry["date"], "%Y-%m-%d").replace(
        hour=hour, tzinfo=timezone.utc
    )
    enclosure_url = f"{RAW_BASE}/audio/{filename}"
    guid = filename
    return f"""    <item>
      <title>{escape(title)}</title>
      <guid isPermaLink="false">{escape(guid)}</guid>
      <pubDate>{format_datetime(pub_dt)}</pubDate>
      <itunes:episode>{episode_number}</itunes:episode>
      <itunes:episodeType>full</itunes:episodeType>
      <enclosure url="{escape(enclosure_url)}" length="{size}" type="audio/mpeg" />
      <description>{escape(entry['title'])} ({label}, {entry['date']})</description>
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
