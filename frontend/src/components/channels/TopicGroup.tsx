import { useState } from 'react';
import type { Channel } from '../../types/channel';
import ChannelCard from './ChannelCard';
import ChannelForm from './ChannelForm';

interface TopicGroupProps {
  slug: string;
  description: string | null;
  channels: Channel[];
  onAddChannel: (name: string, url: string) => void;
  onDeleteChannel: (channelName: string) => void;
  onEditTopic: (description: string) => void;
  onDeleteTopic: () => void;
}

export default function TopicGroup({
  slug,
  description,
  channels,
  onAddChannel,
  onDeleteChannel,
  onEditTopic,
  onDeleteTopic,
}: TopicGroupProps) {
  const [expanded, setExpanded] = useState(true);
  const [showChannelForm, setShowChannelForm] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editDesc, setEditDesc] = useState(description || '');

  const canDeleteTopic = channels.length === 0;

  const handleSaveEdit = () => {
    onEditTopic(editDesc);
    setEditing(false);
  };

  return (
    <div className="bg-surface-1 border border-border rounded-lg overflow-hidden">
      {/* Topic header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-surface-2"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-text-muted text-xs">{expanded ? '\u25BC' : '\u25B6'}</span>
          <span className="font-semibold text-text-primary">{slug}</span>
          <span className="text-xs text-text-muted">({channels.length} canal{channels.length !== 1 ? 'es' : ''})</span>
        </div>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-text-muted hover:text-accent transition-colors"
          >
            Editar
          </button>
          <button
            onClick={canDeleteTopic ? onDeleteTopic : undefined}
            className={`text-xs transition-colors ${
              canDeleteTopic
                ? 'text-text-muted hover:text-danger'
                : 'text-text-muted cursor-not-allowed'
            }`}
            title={canDeleteTopic ? 'Eliminar topic' : 'No se puede eliminar un topic con canales'}
          >
            Borrar
          </button>
        </div>
      </div>

      {/* Description / edit */}
      {editing ? (
        <div className="px-4 pb-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex gap-2">
            <input
              type="text"
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              className="flex-1 px-2 py-1 bg-surface-2 border border-border rounded text-sm text-text-primary focus:outline-none focus:border-accent/50"
              autoFocus
            />
            <button onClick={handleSaveEdit} className="text-xs text-accent hover:text-accent-hover">
              Guardar
            </button>
            <button onClick={() => setEditing(false)} className="text-xs text-text-muted hover:text-text-secondary">
              Cancelar
            </button>
          </div>
        </div>
      ) : description ? (
        <p className="px-4 pb-2 text-xs text-text-muted">{description}</p>
      ) : null}

      {/* Channels list */}
      {expanded && (
        <div className="px-4 pb-4 space-y-2">
          {channels.map((ch) => (
            <ChannelCard
              key={ch.id}
              channel={ch}
              onDelete={() => onDeleteChannel(ch.name)}
            />
          ))}

          {showChannelForm ? (
            <ChannelForm
              onSubmit={(name, url) => {
                onAddChannel(name, url);
                setShowChannelForm(false);
              }}
              onCancel={() => setShowChannelForm(false)}
            />
          ) : (
            <button
              onClick={() => setShowChannelForm(true)}
              className="text-xs text-accent hover:text-accent-hover transition-colors"
            >
              + Anadir canal
            </button>
          )}
        </div>
      )}
    </div>
  );
}
