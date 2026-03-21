import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStrategies, getStrategy } from '../services/strategies';
import { getResearchSessions } from '../services/research';
import StrategyCard from '../components/strategies/StrategyCard';
import StrategyDetail from '../components/strategies/StrategyDetail';
import LoadingSpinner from '../components/common/LoadingSpinner';
import type { Strategy } from '../types/strategy';

type Tab = 'pending' | 'ideas' | 'estrategias';
type StrategiaSubTab = 'con_todos' | 'completas';

export default function StrategiesPage() {
  const [tab, setTab] = useState<Tab>('pending');
  const [estrategiasSubTab, setEstrategiasSubTab] = useState<StrategiaSubTab>('con_todos');
  const [search, setSearch] = useState('');
  const [channelFilter, setChannelFilter] = useState('');
  const [sessionFilter, setSessionFilter] = useState('');
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const { data: sessionsData } = useQuery({
    queryKey: ['research-sessions-strategies'],
    queryFn: () => getResearchSessions(50),
  });

  // Pendientes tab: strategies with status='pending'
  const { data: pendingData, isLoading: loadingPending } = useQuery({
    queryKey: ['pending-strategies', search, channelFilter, sessionFilter],
    queryFn: () => getStrategies({
      search: search || undefined,
      channel: channelFilter || undefined,
      session_id: sessionFilter ? Number(sessionFilter) : undefined,
      status: 'pending',
    }),
    enabled: tab === 'pending',
  });

  // Ideas tab: strategies with status='idea'
  const { data: ideasData, isLoading: loadingIdeas } = useQuery({
    queryKey: ['ideas', search, channelFilter, sessionFilter],
    queryFn: () => getStrategies({
      search: search || undefined,
      channel: channelFilter || undefined,
      session_id: sessionFilter ? Number(sessionFilter) : undefined,
      status: 'idea',
    }),
    enabled: tab === 'ideas',
  });

  // Estrategias tab: sub-tab "con_todos" (validated + has_todos=true)
  const { data: conTodosData, isLoading: loadingConTodos } = useQuery({
    queryKey: ['validated-strategies-con-todos', search, channelFilter, sessionFilter],
    queryFn: () => getStrategies({
      search: search || undefined,
      channel: channelFilter || undefined,
      session_id: sessionFilter ? Number(sessionFilter) : undefined,
      status: 'validated',
      has_todos: true,
    }),
    enabled: tab === 'estrategias' && estrategiasSubTab === 'con_todos',
  });

  // Estrategias tab: sub-tab "completas" (validated + has_todos=false)
  const { data: completasData, isLoading: loadingCompletas } = useQuery({
    queryKey: ['validated-strategies-completas', search, channelFilter, sessionFilter],
    queryFn: () => getStrategies({
      search: search || undefined,
      channel: channelFilter || undefined,
      session_id: sessionFilter ? Number(sessionFilter) : undefined,
      status: 'validated',
      has_todos: false,
    }),
    enabled: tab === 'estrategias' && estrategiasSubTab === 'completas',
  });

  const estrategiasData = estrategiasSubTab === 'con_todos' ? conTodosData : completasData;
  const loadingFinales = estrategiasSubTab === 'con_todos' ? loadingConTodos : loadingCompletas;

  const handleStrategyClick = async (name: string) => {
    setLoadingDetail(true);
    try {
      const detail = await getStrategy(name);
      setSelectedStrategy(detail);
    } finally {
      setLoadingDetail(false);
    }
  };

  // Collect unique channels from the active tab's data
  const activeData = tab === 'pending' ? pendingData : tab === 'ideas' ? ideasData : estrategiasData;
  const channels = Array.from(
    new Set(
      (activeData?.strategies ?? [])
        .map((s) => s.source_channel)
        .filter((c): c is string => !!c)
    )
  );

  const activeLoading = tab === 'pending' ? loadingPending : tab === 'ideas' ? loadingIdeas : loadingFinales;

  const emptyMessages: Record<Tab, string> = {
    pending: 'No hay estrategias pendientes de revision',
    ideas: 'No hay ideas todavia. Valida estrategias desde la pestana Pendientes.',
    estrategias: estrategiasSubTab === 'con_todos'
      ? 'No hay estrategias validadas con TODOs pendientes'
      : 'No hay estrategias validadas completas todavia',
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-white">Resultados</h1>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-800 border border-slate-700 rounded-lg p-1 w-fit">
        <button
          onClick={() => { setTab('pending'); setSelectedStrategy(null); }}
          className={`px-4 py-1.5 text-sm rounded transition-colors ${
            tab === 'pending' ? 'bg-primary-600 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          Pendientes
        </button>
        <button
          onClick={() => { setTab('ideas'); setSelectedStrategy(null); }}
          className={`px-4 py-1.5 text-sm rounded transition-colors ${
            tab === 'ideas' ? 'bg-primary-600 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          Ideas
        </button>
        <button
          onClick={() => { setTab('estrategias'); setSelectedStrategy(null); }}
          className={`px-4 py-1.5 text-sm rounded transition-colors ${
            tab === 'estrategias' ? 'bg-primary-600 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          Estrategias
        </button>
      </div>

      {tab === 'estrategias' && (
        <div className="flex gap-1 bg-slate-900 border border-slate-700 rounded-md p-0.5 w-fit ml-1">
          <button
            onClick={() => { setEstrategiasSubTab('con_todos'); setSelectedStrategy(null); }}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              estrategiasSubTab === 'con_todos' ? 'bg-amber-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            Con TODOs
          </button>
          <button
            onClick={() => { setEstrategiasSubTab('completas'); setSelectedStrategy(null); }}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              estrategiasSubTab === 'completas' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            Completas
          </button>
        </div>
      )}

      {/* Filters (shared between all tabs) */}
      <div className="flex gap-3 flex-wrap">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar..."
          className="flex-1 max-w-xs px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-primary-500"
        />
        <select
          value={channelFilter}
          onChange={(e) => setChannelFilter(e.target.value)}
          className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:border-primary-500"
        >
          <option value="">Canal: Todos</option>
          {channels.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={sessionFilter}
          onChange={(e) => setSessionFilter(e.target.value)}
          className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-slate-100 focus:outline-none focus:border-primary-500"
        >
          <option value="">Sesion: Todas</option>
          {(sessionsData?.sessions ?? []).map((s) => (
            <option key={s.id} value={String(s.id)}>
              {s.topic ?? 'Sin topic'} -{' '}
              {s.started_at
                ? new Date(s.started_at).toLocaleDateString('es-ES')
                : '-'}
            </option>
          ))}
        </select>
      </div>

      {/* Tab content */}
      {activeLoading ? (
        <LoadingSpinner />
      ) : selectedStrategy ? (
        <StrategyDetail
          strategy={selectedStrategy}
          onClose={() => setSelectedStrategy(null)}
          onStatusChange={() => setSelectedStrategy(null)}
        />
      ) : (
        <>
          <p className="text-sm text-slate-400">
            {(activeData?.total ?? 0) === 0
              ? emptyMessages[tab]
              : `Total: ${activeData?.total ?? 0} ${tab === 'pending' ? 'pendientes' : tab === 'ideas' ? 'ideas' : 'estrategias validadas'}`}
          </p>
          <div className="space-y-3">
            {(activeData?.strategies ?? []).map((s) => (
              <StrategyCard
                key={s.id}
                strategy={s}
                onClick={() => handleStrategyClick(s.name)}
              />
            ))}
          </div>
        </>
      )}

      {loadingDetail && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <LoadingSpinner />
        </div>
      )}
    </div>
  );
}
