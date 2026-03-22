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
    <form onSubmit={handleSubmit} className="bg-surface-2/50 border border-border rounded p-4 space-y-3">
      {!editMode && (
        <div>
          <label className="block text-xs text-text-muted mb-1">Slug</label>
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="e.g: futures"
            className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/50"
            required
            autoFocus
          />
        </div>
      )}
      <div>
        <label className="block text-xs text-text-muted mb-1">Description</label>
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g: Futures strategies"
          className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/50"
          autoFocus={editMode}
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          className="px-3 py-1.5 text-sm bg-accent hover:bg-accent-hover text-text-primary rounded transition-colors"
        >
          {editMode ? 'Save' : 'Create'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-3 text-text-secondary rounded transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
