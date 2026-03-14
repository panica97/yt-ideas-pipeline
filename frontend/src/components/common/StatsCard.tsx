interface StatsCardProps {
  icon: string;
  label: string;
  value: number;
  color?: string;
}

export default function StatsCard({ icon, label, value, color = 'text-primary-400' }: StatsCardProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
      <div className="flex items-center gap-3">
        <span className={`text-2xl ${color}`}>{icon}</span>
        <div>
          <p className="text-sm text-slate-400">{label}</p>
          <p className="text-2xl font-bold text-white">{value}</p>
        </div>
      </div>
    </div>
  );
}
