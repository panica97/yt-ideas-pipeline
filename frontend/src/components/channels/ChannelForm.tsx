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
    <form onSubmit={handleSubmit} className="bg-slate-700/50 border border-slate-600 rounded p-4 space-y-3">
      <div>
        <label className="block text-xs text-slate-400 mb-1">Nombre del canal</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="ej: Jacob Amaral"
          className="w-full px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-primary-500"
          required
          autoFocus
        />
      </div>
      <div>
        <label className="block text-xs text-slate-400 mb-1">URL de YouTube</label>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/@canal"
          className="w-full px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-primary-500"
          required
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          className="px-3 py-1.5 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded transition-colors"
        >
          Anadir
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-sm bg-slate-600 hover:bg-slate-500 text-slate-300 rounded transition-colors"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
