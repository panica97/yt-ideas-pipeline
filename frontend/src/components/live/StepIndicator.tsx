interface StepIndicatorProps {
  status: 'running' | 'completed' | 'error';
}

export default function StepIndicator({ status }: StepIndicatorProps) {
  let dotClass = 'bg-surface-3';
  if (status === 'running') {
    dotClass = 'bg-green-400 animate-pulse';
  } else if (status === 'completed') {
    dotClass = 'bg-green-400';
  } else if (status === 'error') {
    dotClass = 'bg-red-400';
  }

  return <span className={`inline-block w-3 h-3 rounded-full ${dotClass}`} />;
}
