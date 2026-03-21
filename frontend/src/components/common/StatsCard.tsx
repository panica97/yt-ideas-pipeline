import type { LucideIcon } from 'lucide-react';

interface StatsCardProps {
  icon: LucideIcon;
  label: string;
  value: number;
  color?: 'accent' | 'warn' | 'danger' | 'default';
}

const colorMap = {
  default: {
    icon: 'text-accent',
    iconBg: 'bg-accent/10',
    glow: '',
  },
  accent: {
    icon: 'text-accent',
    iconBg: 'bg-accent/10',
    glow: 'hover:shadow-glow-accent',
  },
  warn: {
    icon: 'text-warn',
    iconBg: 'bg-warn/10',
    glow: 'hover:shadow-glow-warn',
  },
  danger: {
    icon: 'text-danger',
    iconBg: 'bg-danger/10',
    glow: 'hover:shadow-glow-danger',
  },
};

export default function StatsCard({ icon: Icon, label, value, color = 'default' }: StatsCardProps) {
  const colors = colorMap[color];

  return (
    <div className={`card p-5 transition-all duration-300 ${colors.glow}`}>
      <div className="flex items-center gap-4">
        <div className={`w-10 h-10 rounded-lg ${colors.iconBg} flex items-center justify-center`}>
          <Icon size={20} className={colors.icon} />
        </div>
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold text-text-primary font-mono mt-0.5">{value}</p>
        </div>
      </div>
    </div>
  );
}
