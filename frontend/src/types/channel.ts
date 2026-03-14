export interface Channel {
  id: number;
  name: string;
  url: string;
  last_fetched: string | null;
  created_at: string | null;
}

export interface TopicWithChannels {
  description: string | null;
  channels: Channel[];
}

export interface ChannelsResponse {
  topics: Record<string, TopicWithChannels>;
}

export interface Topic {
  id: number;
  slug: string;
  description: string | null;
}
