import { useState } from 'react';

interface TopicFormProps {
  onSubmit: (slug: string, description: string) => void;
  onCancel: () => void;
  initialSlug?: string;
  initialDescription?: string;
  editMode?: boolean;
}

export default function TopicForm({
  onSubmit,
  onCancel,
  initialSlug = '',
  initialDescription = '',
  editMode = false,
}: TopicFormProps) {
  const [slug, setSlug] = useState(initialSlug);
  const [description, setDescription] = useState(initialDescription);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(slug.trim(), description.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="bg-slate-700/50 border border-slate-600 rounded p-4 space-y-3">
      {!editMode && (
        <div>
          <label className="block text-xs text-slate-400 mb-1">Slug</label>
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="ej: futures"
            className="w-full px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-primary-500"
            required
            autoFocus
          />
        </div>
      )}
      <div>
        <label className="block text-xs text-slate-400 mb-1">Descripcion</label>
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="ej: Estrategias de futuros"
          className="w-full px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-primary-500"
          autoFocus={editMode}
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          className="px-3 py-1.5 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded transition-colors"
        >
          {editMode ? 'Guardar' : 'Crear'}
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
