import { NavLink } from 'react-router-dom';

const navItems = [
  { to: '/', label: 'Dashboard', icon: '\u2302' },
  { to: '/research', label: 'Investigaciones', icon: '\uD83D\uDD2C' },
  { to: '/channels', label: 'Canales', icon: '\u25B6' },
  { to: '/history', label: 'Historial', icon: '\u23F0' },
  { to: '/strategies', label: 'Estrategias', icon: '\u2605' },
  { to: '/live', label: 'Live', icon: '\u26A1' },
];

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-slate-800 border-r border-slate-700 flex flex-col z-20">
      <div className="p-4 border-b border-slate-700">
        <h1 className="text-lg font-bold text-white tracking-wide">IRT</h1>
        <p className="text-xs text-slate-400">Ideas Research Team</p>
      </div>
      <nav className="flex-1 py-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                isActive
                  ? 'bg-primary-600/20 text-primary-400 border-r-2 border-primary-400'
                  : 'text-slate-300 hover:bg-slate-700/50 hover:text-white'
              }`
            }
          >
            <span className="text-lg">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="p-4 border-t border-slate-700">
        <button
          onClick={() => {
            localStorage.removeItem('irt_api_key');
            window.location.href = '/login';
          }}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          Cerrar sesion
        </button>
      </div>
    </aside>
  );
}
