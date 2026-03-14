"""Pydantic v2 schemas for channels."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

_YT_URL_RE = re.compile(
    r"^https?://(www\.)?youtube\.com/(@[\w.-]+|c/[\w.-]+|channel/[\w-]+)"
)


class ChannelCreate(BaseModel):
    name: str
    url: str

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        v = v.strip()
        if not _YT_URL_RE.match(v):
            raise ValueError(
                "La URL debe ser un canal de YouTube valido "
                "(youtube.com/@..., /c/..., o /channel/...)"
            )
        return v


class ChannelResponse(BaseModel):
    id: int
    name: str
    url: str
    last_fetched: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TopicWithChannels(BaseModel):
    description: str | None = None
    channels: list[ChannelResponse] = []


class ChannelsListResponse(BaseModel):
    topics: dict[str, TopicWithChannels] = {}
