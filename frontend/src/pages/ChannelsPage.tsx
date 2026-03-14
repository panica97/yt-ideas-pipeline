import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getChannels,
  createTopic,
  updateTopic,
  deleteTopic,
  createChannel,
  deleteChannel,
} from '../services/channels';
import TopicGroup from '../components/channels/TopicGroup';
import TopicForm from '../components/channels/TopicForm';
import ConfirmDialog from '../components/common/ConfirmDialog';
import LoadingSpinner from '../components/common/LoadingSpinner';

export default function ChannelsPage() {
  const queryClient = useQueryClient();
  const [showTopicForm, setShowTopicForm] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<{
    type: 'topic' | 'channel';
    topic: string;
    channel?: string;
  } | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['channels'] });

  const createTopicMut = useMutation({
    mutationFn: (vars: { slug: string; description: string }) =>
      createTopic(vars.slug, vars.description),
    onSuccess: () => {
      invalidate();
      setShowTopicForm(false);
    },
  });

  const updateTopicMut = useMutation({
    mutationFn: (vars: { slug: string; description: string }) =>
      updateTopic(vars.slug, vars.description),
    onSuccess: invalidate,
  });

  const deleteTopicMut = useMutation({
    mutationFn: (slug: string) => deleteTopic(slug),
    onSuccess: invalidate,
  });

  const createChannelMut = useMutation({
    mutationFn: (vars: { topic: string; name: string; url: string }) =>
      createChannel(vars.topic, vars.name, vars.url),
    onSuccess: invalidate,
  });

  const deleteChannelMut = useMutation({
    mutationFn: (vars: { topic: string; channelName: string }) =>
      deleteChannel(vars.topic, vars.channelName),
    onSuccess: invalidate,
  });

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    return (
      <div className="text-red-400 text-sm">
        Error al cargar canales: {(error as Error).message}
      </div>
    );
  }

  const topics = data?.topics ?? {};

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Canales</h1>
        <button
          onClick={() => setShowTopicForm(true)}
          className="px-3 py-1.5 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded transition-colors"
        >
          + Anadir topic
        </button>
      </div>

      {showTopicForm && (
        <TopicForm
          onSubmit={(slug, desc) =>
            createTopicMut.mutate({ slug, description: desc })
          }
          onCancel={() => setShowTopicForm(false)}
        />
      )}

      {createTopicMut.isError && (
        <p className="text-sm text-red-400">
          Error: {(createTopicMut.error as Error).message}
        </p>
      )}

      {Object.keys(topics).length === 0 && !showTopicForm && (
        <p className="text-sm text-slate-500">No hay topics registrados. Crea uno para empezar.</p>
      )}

      <div className="space-y-3">
        {Object.entries(topics).map(([slug, topicData]) => (
          <TopicGroup
            key={slug}
            slug={slug}
            description={topicData.description}
            channels={topicData.channels}
            onAddChannel={(name, url) =>
              createChannelMut.mutate({ topic: slug, name, url })
            }
            onDeleteChannel={(channelName) =>
              setConfirmDelete({ type: 'channel', topic: slug, channel: channelName })
            }
            onEditTopic={(description) =>
              updateTopicMut.mutate({ slug, description })
            }
            onDeleteTopic={() =>
              setConfirmDelete({ type: 'topic', topic: slug })
            }
          />
        ))}
      </div>

      <ConfirmDialog
        open={confirmDelete !== null}
        title={confirmDelete?.type === 'topic' ? 'Eliminar topic' : 'Eliminar canal'}
        message={
          confirmDelete?.type === 'topic'
            ? `Seguro que quieres eliminar el topic "${confirmDelete.topic}"?`
            : `Seguro que quieres eliminar el canal "${confirmDelete?.channel}" del topic "${confirmDelete?.topic}"?`
        }
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (confirmDelete?.type === 'topic') {
            deleteTopicMut.mutate(confirmDelete.topic);
          } else if (confirmDelete?.type === 'channel' && confirmDelete.channel) {
            deleteChannelMut.mutate({
              topic: confirmDelete.topic,
              channelName: confirmDelete.channel,
            });
          }
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
