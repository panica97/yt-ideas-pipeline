"""Channel CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, verify_api_key
from api.models.schemas.channel import (
    ChannelCreate,
    ChannelResponse,
    ChannelsListResponse,
    TopicWithChannels,
)
from api.services import channel_service

router = APIRouter(prefix="/api/channels", tags=["channels"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=ChannelsListResponse)
async def list_channels(db: AsyncSession = Depends(get_db)):
    topics = await channel_service.list_all_topics_with_channels(db)
    result: dict[str, TopicWithChannels] = {}
    for topic in topics:
        result[topic.slug] = TopicWithChannels(
            description=topic.description,
            channels=[ChannelResponse.model_validate(ch) for ch in topic.channels],
        )
    return ChannelsListResponse(topics=result)


@router.get("/{topic}", response_model=TopicWithChannels)
async def get_channels_for_topic(topic: str, db: AsyncSession = Depends(get_db)):
    t = await channel_service.get_topic_with_channels(db, topic)
    return TopicWithChannels(
        description=t.description,
        channels=[ChannelResponse.model_validate(ch) for ch in t.channels],
    )


@router.post("/{topic}", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def add_channel(topic: str, body: ChannelCreate, db: AsyncSession = Depends(get_db)):
    channel = await channel_service.add_channel(db, topic, body.name, body.url)
    return channel


@router.delete("/{topic}/{channel_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(topic: str, channel_name: str, db: AsyncSession = Depends(get_db)):
    await channel_service.delete_channel(db, topic, channel_name)
