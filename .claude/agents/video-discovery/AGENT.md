---
name: video-discovery
description: Fetch and classify YouTube videos by topic
domain: research
role: agent
inputs:
  - name: topic
    type: string
    required: true
  - name: max_videos
    type: integer
    default: 10
outputs:
  - name: videos
    type: "Video[]"
  - name: stop_signal
    type: string
    enum: [null, NO_VIDEOS_FOUND, NO_NEW_VIDEOS]
skills_used:
  - yt-scraper
  - video-classifier
dependencies: []
---

# Video Discovery Agent

Fetches YouTube videos for a given topic from monitored channels and classifies them to filter out irrelevant content. Returns only videos likely to contain trading strategies.

This agent is self-contained. It does not know about sessions, DB persistence, strategy extraction, or any downstream processing.

## How to Use

Given a `topic` string (a slug matching a topic in `data/channels/channels.yaml`), this agent fetches recent videos from registered channels for that topic, filters out already-researched videos, classifies the remaining ones by title relevance, and returns the list of relevant videos.

Optional `max_videos` (default 10) limits how many videos to fetch from yt-dlp.

## Step 1: Fetch Videos (yt-scraper skill)

Read `.claude/skills/yt-scraper/SKILL.md` for the full skill interface.

Run the fetch command:

```bash
python -m tools.youtube.fetch_topic --db data/channels/channels.yaml --count <max_videos> <topic>
```

If `DATABASE_URL` is set, channels are read from PostgreSQL automatically (YAML is fallback).

### Filter already-researched videos

After fetching, filter out videos that have already been researched:

**If DATABASE_URL is set (preferred):**

```python
from tools.db.session import sync_session_ctx
from tools.db.history_repo import get_researched_video_ids

with sync_session_ctx() as session:
    researched_ids = get_researched_video_ids(session, "<topic_slug>")
```

Filter out any videos whose `video_id` already appears in `researched_ids`.

**If DATABASE_URL is NOT set (fallback):**

1. Read `data/research/history.yaml`
2. Extract the `video_id` values from `researched_videos`
3. For each fetched video, extract its `video_id` from the URL (the `v=` parameter)
4. Discard videos whose `video_id` already exists in the history

### Stop signals after fetch

- **No videos at all** from the channel for this topic: return `stop_signal: NO_VIDEOS_FOUND`
- **All videos already researched**: return `stop_signal: NO_NEW_VIDEOS`
- **New videos exist**: proceed to Step 2

### Error handling

- Command fails (exit code != 0): report the error, return `stop_signal: NO_VIDEOS_FOUND`
- Topic does not exist in the channel DB: report available topics, return `stop_signal: NO_VIDEOS_FOUND`
- Database connection error for history check: fall back to YAML history check

## Step 2: Classify Videos (video-classifier skill)

Read `.claude/skills/video-classifier/SKILL.md` for the full skill interface.

Classify each video title yourself (no external script or API call needed). For each video, decide:

- `strategy`: the title suggests a concrete trading strategy, system, method, backtest, algorithm, or setup with indicators
- `irrelevant`: setup tours, Q&As, vlogs, gear reviews, personal stories, market commentary without an actionable strategy

**Conservative rule**: when in doubt, classify as `strategy`. Better to pass a borderline video downstream than miss a real strategy.

### Process

1. Take the new (non-researched) videos from Step 1
2. Classify each title as `strategy` or `irrelevant` with a brief reason (one sentence)
3. Separate videos into two groups: `strategy` and `irrelevant`

### Stop signal after classification

- **All videos are irrelevant**: return `stop_signal: NO_VIDEOS_FOUND` with the classification details
- **At least one video classified as strategy**: continue to output

## Output

Return a structured result with:

```yaml
videos:
  - video_id: "abc123"
    url: "https://youtube.com/watch?v=abc123"
    title: "Building an RTY Breakout Strategy"
    channel: "Channel Name"
    classification: strategy
    reason: "Describes building a specific trading strategy"
  - video_id: "def456"
    url: "https://youtube.com/watch?v=def456"
    title: "My Trading Desk Setup Tour"
    channel: "Channel Name"
    classification: irrelevant
    reason: "Setup tour, no strategy content"
stop_signal: null
summary:
  total_fetched: <N>
  already_researched: <N>
  classified_strategy: <N>
  classified_irrelevant: <N>
```

The `videos` list contains ONLY the videos classified as `strategy`. Include the irrelevant videos in the classification log for transparency, but they are not part of the output consumed downstream.

If a stop signal is set (`NO_VIDEOS_FOUND` or `NO_NEW_VIDEOS`), the `videos` list is empty.

## Rules

- ONLY fetch videos from channels registered in the DB -- never search YouTube freely
- NEVER skip the history filter -- always check for already-researched videos
- NEVER skip the classification step -- always classify before returning
- Each video in the output must have: `video_id`, `url`, `title`, `channel`
- This agent does not create notebooks, extract strategies, save to DB, or track sessions
