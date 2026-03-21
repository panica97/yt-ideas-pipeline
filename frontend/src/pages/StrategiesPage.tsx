import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStrategies, getStrategy } from '../services/strategies';
import { getResearchSessions } from '../services/research';
import StrategyCard from '../components/strategies/StrategyCard';
import StrategyDetail from '../components/strategies/StrategyDetail';
import LoadingSpinner from '../components/common/LoadingSpinner';
import type { Strategy } from '../types/strategy';
import { Search, Inbox } from 'lucide-react';

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
    <div className="space-y-4 animate-fade-in">
      <h1 className="text-lg font-semibold text-text-primary">Resultados</h1>

      {/* Tabs */}
      <div className="flex gap-1 glass rounded-lg p-1 w-fit">
        {[
          { key: 'pending' as Tab, label: 'Pendientes' },
          { key: 'ideas' as Tab, label: 'Ideas' },
          { key: 'estrategias' as Tab, label: 'Estrategias' },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setSelectedStrategy(null); }}
            className={`px-4 py-1.5 text-sm rounded-md transition-all duration-200 ${
              tab === t.key
                ? 'bg-accent text-text-primary shadow-glow-accent'
                : 'text-text-muted hover:text-text-primary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'estrategias' && (
        <div className="flex gap-1 bg-surface-1 border border-border rounded-md p-0.5 w-fit ml-1">
          <button
            onClick={() => { setEstrategiasSubTab('con_todos'); setSelectedStrategy(null); }}
            className={`px-3 py-1 text-xs rounded transition-all duration-200 ${
              estrategiasSubTab === 'con_todos'
                ? 'bg-warn text-text-primary'
                : 'text-text-muted hover:text-text-primary'
            }`}
          >
            Con TODOs
          </button>
          <button
            onClick={() => { setEstrategiasSubTab('completas'); setSelectedStrategy(null); }}
            className={`px-3 py-1 text-xs rounded transition-all duration-200 ${
              estrategiasSubTab === 'completas'
                ? 'bg-accent text-text-primary'
                : 'text-text-muted hover:text-text-primary'
            }`}
          >
            Completas
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar..."
            className="w-full pl-9 pr-3 py-1.5 bg-surface-2 border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-all"
          />
        </div>
        <select
          value={channelFilter}
          onChange={(e) => setChannelFilter(e.target.value)}
          className="px-3 py-1.5 bg-surface-2 border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent/50 transition-all"
        >
          <option value="">Canal: Todos</option>
          {channels.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={sessionFilter}
          onChange={(e) => setSessionFilter(e.target.value)}
          className="px-3 py-1.5 bg-surface-2 border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent/50 transition-all"
        >
          <option value="">Sesion: Todas</option>
          {(sessionsData?.sessions ?? []).map((s) => (
            <option key={s.id} value={String(s.id)}>
              {s.topic ?? 'Sin topic'} -{' '}
              {s.started_at ? new Date(s.started_at).toLocaleDateString('es-ES') : '-'}
            </option>
          ))}
        </select>
      </div>

      {/* Content */}
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
          {(activeData?.total ?? 0) === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Inbox size={48} className="text-text-muted mb-3" />
              <p className="text-sm text-text-muted">{emptyMessages[tab]}</p>
            </div>
          ) : (
            <>
              <p className="text-xs text-text-muted">
                Total: <span className="font-mono text-text-secondary">{activeData?.total ?? 0}</span>{' '}
                {tab === 'pending' ? 'pendientes' : tab === 'ideas' ? 'ideas' : 'estrategias validadas'}
              </p>
              <div className="space-y-2">
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
        </>
      )}

      {loadingDetail && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <LoadingSpinner />
        </div>
      )}
    </div>
  );
}
