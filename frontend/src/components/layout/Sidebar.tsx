import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FlaskConical,
  Tv,
  Clock,
  Trophy,
  Zap,
  Settings2,
  ChevronsLeft,
  ChevronsRight,
  LogOut,
} from 'lucide-react';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/research', label: 'Investigaciones', icon: FlaskConical },
  { to: '/channels', label: 'Canales', icon: Tv },
  { to: '/history', label: 'Historial', icon: Clock },
  { to: '/strategies', label: 'Resultados', icon: Trophy },
  { to: '/live', label: 'Live', icon: Zap },
  { to: '/instruments', label: 'Instrumentos', icon: Settings2 },
];

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      className={`fixed left-0 top-0 h-screen bg-surface-1 border-r border-border flex flex-col z-30 transition-all duration-300 ease-in-out ${
        collapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Logo */}
      <div className="relative p-4 flex items-center gap-3 min-h-[3.5rem]">
        <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center flex-shrink-0">
          <span className="text-accent font-bold text-sm font-mono">IR</span>
        </div>
        {!collapsed && (
          <div className="animate-fade-in">
            <h1 className="text-sm font-bold text-text-primary tracking-wide">IRT</h1>
            <p className="text-[10px] text-text-muted">Ideas Research Team</p>
          </div>
        )}
        {/* Accent line at bottom */}
        <div className="absolute bottom-0 left-4 right-4 h-px bg-gradient-to-r from-accent/40 via-accent/10 to-transparent" />
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all duration-200 ${
                isActive
                  ? 'bg-accent/10 text-accent'
                  : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r bg-accent shadow-glow-accent" />
                )}
                <item.icon size={18} strokeWidth={isActive ? 2 : 1.5} className="flex-shrink-0" />
                {!collapsed && (
                  <span className="animate-fade-in whitespace-nowrap">{item.label}</span>
                )}
                {/* Tooltip for collapsed state */}
                {collapsed && (
                  <div className="absolute left-full ml-2 px-2 py-1 bg-surface-2 border border-border rounded text-xs text-text-primary whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-200 z-50">
                    {item.label}
                  </div>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom section */}
      <div className="px-2 pb-3 space-y-1">
        {/* Collapse toggle */}
        <button
          onClick={onToggle}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-text-muted hover:text-text-secondary hover:bg-surface-2 transition-colors text-sm"
        >
          {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
          {!collapsed && <span className="animate-fade-in">Colapsar</span>}
        </button>

        {/* Logout */}
        <button
          onClick={() => {
            localStorage.removeItem('irt_api_key');
            window.location.href = '/login';
          }}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-text-muted hover:text-danger hover:bg-danger/10 transition-colors text-sm"
        >
          <LogOut size={18} />
          {!collapsed && <span className="animate-fade-in">Cerrar sesion</span>}
        </button>
      </div>
    </aside>
  );
}
