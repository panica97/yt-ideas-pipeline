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
            raise ValueError("El slug no puede estar vacio")
        if len(v) > 50:
            raise ValueError("El slug no puede superar 50 caracteres")
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError(
                "El slug debe ser minusculas, sin espacios "
                "(solo letras, numeros y guiones)"
            )
        return v


class TopicUpdate(BaseModel):
    description: str


class TopicResponse(BaseModel):
    id: int
    slug: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)
