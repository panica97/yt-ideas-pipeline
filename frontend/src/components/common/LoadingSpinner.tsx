export default function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="w-8 h-8 border-2 border-slate-600 border-t-primary-400 rounded-full animate-spin" />
    </div>
  );
}
