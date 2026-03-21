export default function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="relative">
        <div className="w-8 h-8 border-2 border-surface-3 rounded-full" />
        <div className="absolute inset-0 w-8 h-8 border-2 border-transparent border-t-accent rounded-full animate-spin" />
      </div>
    </div>
  );
}
