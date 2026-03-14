"""Pydantic v2 schemas for export."""

from __future__ import annotations

from enum import Enum


class ExportFormat(str, Enum):
    yaml = "yaml"
    json = "json"
