import { useState } from 'react';

interface ChannelFormProps {
  onSubmit: (name: string, url: string) => void;
  onCancel: () => void;
}

export default function ChannelForm({ onSubmit, onCancel }: ChannelFormProps) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(name.trim(), url.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="bg-surface-2/50 border border-border rounded p-4 space-y-3">
      <div>
        <label className="block text-xs text-text-muted mb-1">Nombre del canal</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="ej: Jacob Amaral"
          className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/50"
          required
          autoFocus
        />
      </div>
      <div>
        <label className="block text-xs text-text-muted mb-1">URL de YouTube</label>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/@canal"
          className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/50"
          required
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          className="px-3 py-1.5 text-sm bg-accent hover:bg-accent-hover text-text-primary rounded transition-colors"
        >
          Anadir
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-3 text-text-secondary rounded transition-colors"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
