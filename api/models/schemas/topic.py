"""Pydantic v2 schemas for topics."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator


class TopicCreate(BaseModel):
    slug: str
    description: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Slug cannot be empty")
        if len(v) > 50:
            raise ValueError("Slug cannot exceed 50 characters")
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError(
                "Slug must be lowercase, no spaces "
                "(only letters, numbers, and hyphens)"
            )
        return v


class TopicUpdate(BaseModel):
    description: str


class TopicResponse(BaseModel):
    id: int
    slug: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)
