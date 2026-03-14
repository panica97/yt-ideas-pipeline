"""Topic CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, verify_api_key
from api.models.schemas.topic import TopicCreate, TopicResponse, TopicUpdate
from api.services import topic_service

router = APIRouter(prefix="/api/topics", tags=["topics"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(body: TopicCreate, db: AsyncSession = Depends(get_db)):
    topic = await topic_service.create_topic(db, body.slug, body.description)
    return topic


@router.put("/{slug}", response_model=TopicResponse)
async def update_topic(slug: str, body: TopicUpdate, db: AsyncSession = Depends(get_db)):
    topic = await topic_service.update_topic(db, slug, body.description)
    return topic


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(slug: str, db: AsyncSession = Depends(get_db)):
    await topic_service.delete_topic(db, slug)
