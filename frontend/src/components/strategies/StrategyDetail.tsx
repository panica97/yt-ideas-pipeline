import type { Strategy } from '../../types/strategy';

interface StrategyDetailProps {
  strategy: Strategy;
  onClose: () => void;
}

function RuleList({ title, rules }: { title: string; rules: Record<string, unknown>[] | null }) {
  if (!rules || rules.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">{title}</h4>
      <ul className="space-y-1">
        {rules.map((rule, i) => (
          <li key={i} className="text-sm text-slate-300 bg-slate-700/30 rounded px-3 py-1.5">
            {typeof rule === 'string' ? rule : JSON.stringify(rule)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function StrategyDetail({ strategy, onClose }: StrategyDetailProps) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-semibold text-white">{strategy.name}</h3>
          {strategy.source_channel && (
            <p className="text-xs text-primary-400 mt-0.5">{strategy.source_channel}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-300 text-sm transition-colors"
        >
          Cerrar
        </button>
      </div>

      {strategy.description && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 uppercase mb-1">Descripcion</h4>
          <p className="text-sm text-slate-300 leading-relaxed">{strategy.description}</p>
        </div>
      )}

      {/* Parameters table */}
      {strategy.parameters && strategy.parameters.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">Parametros</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-1 px-2 text-slate-500">Nombre</th>
                  <th className="text-left py-1 px-2 text-slate-500">Tipo</th>
                  <th className="text-left py-1 px-2 text-slate-500">Default</th>
                  <th className="text-left py-1 px-2 text-slate-500">Rango</th>
                </tr>
              </thead>
              <tbody>
                {strategy.parameters.map((param, i) => (
                  <tr key={i} className="border-b border-slate-700/50">
                    <td className="py-1 px-2 text-slate-300">{String(param.name || param.parameter || '-')}</td>
                    <td className="py-1 px-2 text-slate-400">{String(param.type || '-')}</td>
                    <td className="py-1 px-2 text-slate-400">{String(param.default ?? '-')}</td>
                    <td className="py-1 px-2 text-slate-400">{String(param.range || '-')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <RuleList title="Reglas de entrada" rules={strategy.entry_rules} />
      <RuleList title="Reglas de salida" rules={strategy.exit_rules} />
      <RuleList title="Gestion de riesgo" rules={strategy.risk_management} />
      <RuleList title="Notas" rules={strategy.notes} />

      {/* Source videos */}
      {strategy.source_videos && strategy.source_videos.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-slate-400 uppercase mb-2">Videos fuente</h4>
          <div className="flex flex-wrap gap-2">
            {strategy.source_videos.map((vid, i) => (
              <a
                key={i}
                href={vid.startsWith('http') ? vid : `https://www.youtube.com/watch?v=${vid}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-primary-400 hover:text-primary-300 bg-slate-700/50 rounded px-2 py-1"
              >
                {vid.startsWith('http') ? new URL(vid).searchParams.get('v') || vid : vid}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
