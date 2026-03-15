import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getStrategies, getStrategy, getDrafts, getDraft } from '../services/strategies';
import { getResearchSessions } from '../services/research';
import StrategyCard from '../components/strategies/StrategyCard';
import StrategyDetail from '../components/strategies/StrategyDetail';
import DraftCard from '../components/strategies/DraftCard';
import DraftDetail from '../components/strategies/DraftDetail';
import LoadingSpinner from '../components/common/LoadingSpinner';
import type { Strategy } from '../types/strategy';
import type { DraftDetail as DraftDetailType } from '../types/draft';

type Tab = 'strategies' | 'drafts';

export default function StrategiesPage() {
  const [tab, setTab] = useState<Tab>('strategies');
  const [search, setSearch] = useState('');
  const [channelFilter, setChannelFilter] = useState('');
  const [sessionFilter, setSessionFilter] = useState('');
  const [todosOnly, setTodosOnly] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [selectedDraft, setSelectedDraft] = useState<DraftDetailType | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const { data: sessionsData } = useQuery({
    queryKey: ['research-sessions-strategies'],
    queryFn: () => getResearchSessions(50),
  });

  const { data: strategiesData, isLoading: loadingStrategies } = useQuery({
    queryKey: ['strategies', search, channelFilter, sessionFilter],
    queryFn: () => getStrategies({
      search: search || undefined,
      channel: channelFilter || undefined,
      session_id: sessionFilter ? Number(sessionFilter) : undefined,
    }),
    enabled: tab === 'strategies',
  });

  const { data: draftsData, isLoading: loadingDrafts } = useQuery({
    queryKey: ['drafts', todosOnly],
    queryFn: () => getDrafts(todosOnly ? true : undefined),
    enabled: tab === 'drafts',
  });

  const handleStrategyClick = async (name: string) => {
    setLoadingDetail(true);
    try {
      const detail = await getStrategy(name);
      setSelectedStrategy(detail);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleDraftClick = async (stratCode: number) => {
    setLoadingDetail(true);
    try {
      const detail = await getDraft(stratCode);
      setSelectedDraft(detail);
    } finally {
      setLoadingDetail(false);
    }
  };

  // Collect unique channels from strategies
  const channels = Array.from(
    new Set(
      (strategiesData?.strategies ?? [])
        .map((s) => s.source_channel)
        .filter((c): c is string => !!c)
    )
  );

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-white">Estrategias</h1>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-800 border border-slate-700 rounded-lg p-1 w-fit">
        <button
          onClick={() => { setTab('strategies'); setSelectedStrategy(null); setSelectedDraft(null); }}
          className={`px-4 py-1.5 text-sm rounded transition-colors ${
            tab === 'strategies' ? 'bg-primary-600 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          Estrategias YAML
        </button>
        <button
          onClick={() => { setTab('drafts'); setSelectedStrategy(null); setSelectedDraft(null); }}
          className={`px-4 py-1.5 text-sm rounded transition-colors ${
            tab === 'drafts' ? 'bg-primary-600 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          Borradores JSON
        </button>
      </div>

      {/* Strategies tab */}
      {tab === 'strategies' && (
        <>
          {/* Filters */}
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

          {loadingStrategies ? (
            <LoadingSpinner />
          ) : selectedStrategy ? (
            <StrategyDetail
              strategy={selectedStrategy}
              onClose={() => setSelectedStrategy(null)}
            />
          ) : (
            <>
              <p className="text-sm text-slate-400">
                Total: {strategiesData?.total ?? 0} estrategias
              </p>
              <div className="space-y-3">
                {(strategiesData?.strategies ?? []).map((s) => (
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

      {/* Drafts tab */}
      {tab === 'drafts' && (
        <>
          {/* Filter */}
          <div className="flex gap-3 items-center">
            <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={todosOnly}
                onChange={(e) => setTodosOnly(e.target.checked)}
                className="rounded bg-slate-700 border-slate-600"
              />
              Solo con TODOs
            </label>
          </div>

          {loadingDrafts ? (
            <LoadingSpinner />
          ) : selectedDraft ? (
            <DraftDetail
              draft={selectedDraft}
              onClose={() => setSelectedDraft(null)}
            />
          ) : (
            <>
              <p className="text-sm text-slate-400">
                Total: {draftsData?.total ?? 0} borradores
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(draftsData?.drafts ?? []).map((d) => (
                  <DraftCard
                    key={d.strat_code}
                    draft={d}
                    onClick={() => handleDraftClick(d.strat_code)}
                  />
                ))}
              </div>
            </>
          )}
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
