import { AlertTriangle } from 'lucide-react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: 'danger' | 'success' | 'primary';
  onConfirm: () => void;
  onCancel: () => void;
}

const variantClasses = {
  danger: 'bg-danger hover:bg-danger-hover',
  success: 'bg-accent hover:bg-accent-hover',
  primary: 'bg-accent hover:bg-accent-hover',
};

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmVariant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in">
      <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative glass rounded-xl p-6 max-w-sm w-full mx-4 shadow-glow-accent animate-slide-in">
        <div className="flex items-start gap-3 mb-4">
          {confirmVariant === 'danger' && (
            <div className="w-10 h-10 rounded-lg bg-danger/10 flex items-center justify-center flex-shrink-0">
              <AlertTriangle size={20} className="text-danger" />
            </div>
          )}
          <div>
            <h3 className="text-base font-semibold text-text-primary">{title}</h3>
            <p className="text-sm text-text-secondary mt-1">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary bg-surface-2 hover:bg-surface-3 rounded-lg transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 text-sm text-text-primary rounded-lg transition-colors ${variantClasses[confirmVariant]}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
