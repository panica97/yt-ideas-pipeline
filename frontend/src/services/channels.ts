import api from './api';
import type { ChannelsResponse, Topic } from '../types/channel';

export async function getChannels(): Promise<ChannelsResponse> {
  const { data } = await api.get<ChannelsResponse>('/channels');
  return data;
}

export async function createTopic(slug: string, description?: string): Promise<Topic> {
  const { data } = await api.post<Topic>('/topics', { slug, description });
  return data;
}

export async function updateTopic(slug: string, description: string): Promise<Topic> {
  const { data } = await api.put<Topic>(`/topics/${slug}`, { description });
  return data;
}

export async function deleteTopic(slug: string): Promise<void> {
  await api.delete(`/topics/${slug}`);
}

export async function createChannel(topic: string, name: string, url: string): Promise<void> {
  await api.post(`/channels/${topic}`, { name, url });
}

export async function deleteChannel(topic: string, channelName: string): Promise<void> {
  await api.delete(`/channels/${topic}/${encodeURIComponent(channelName)}`);
}
