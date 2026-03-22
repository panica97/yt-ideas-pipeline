import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getInstruments,
  createInstrument,
  updateInstrument,
  deleteInstrument,
} from '../services/instruments';
import type { Instrument } from '../types/instrument';
import ConfirmDialog from '../components/common/ConfirmDialog';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { Plus, Pencil, Trash2, Package, X } from 'lucide-react';

type FormData = {
  symbol: string;
  sec_type: string;
  exchange: string;
  currency: string;
  multiplier: string;
  min_tick: string;
  description: string;
};

const emptyForm: FormData = {
  symbol: '',
  sec_type: 'FUT',
  exchange: '',
  currency: 'USD',
  multiplier: '1',
  min_tick: '0.01',
  description: '',
};

const SEC_TYPES = ['FUT', 'STK', 'OPT', 'CASH'];

const secTypeBadge: Record<string, string> = {
  FUT: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
  STK: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  OPT: 'bg-purple-500/15 text-purple-400 border-purple-500/20',
  CASH: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/20',
};

export default function InstrumentsPage() {
  const queryClient = useQueryClient();
  const [editingSymbol, setEditingSymbol] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormData>(emptyForm);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['instruments'],
    queryFn: getInstruments,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['instruments'] });

  const createMut = useMutation({
    mutationFn: (payload: Omit<Instrument, 'id' | 'created_at' | 'updated_at'>) =>
      createInstrument(payload),
    onSuccess: () => {
      invalidate();
      resetForm();
    },
  });

  const updateMut = useMutation({
    mutationFn: (vars: { symbol: string; updates: Partial<Instrument> }) =>
      updateInstrument(vars.symbol, vars.updates),
    onSuccess: () => {
      invalidate();
      resetForm();
    },
  });

  const deleteMut = useMutation({
    mutationFn: (symbol: string) => deleteInstrument(symbol),
    onSuccess: invalidate,
  });

  function resetForm() {
    setForm(emptyForm);
    setShowForm(false);
    setEditingSymbol(null);
  }

  function startEdit(inst: Instrument) {
    setForm({
      symbol: inst.symbol,
      sec_type: inst.sec_type,
      exchange: inst.exchange,
      currency: inst.currency,
      multiplier: String(inst.multiplier),
      min_tick: String(inst.min_tick),
      description: inst.description ?? '',
    });
    setEditingSymbol(inst.symbol);
    setShowForm(true);
  }

  function startCreate() {
    setForm(emptyForm);
    setEditingSymbol(null);
    setShowForm(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      symbol: form.symbol.toUpperCase().trim(),
      sec_type: form.sec_type,
      exchange: form.exchange.toUpperCase().trim(),
      currency: form.currency.toUpperCase().trim(),
      multiplier: parseFloat(form.multiplier) || 1,
      min_tick: parseFloat(form.min_tick) || 0.01,
      description: form.description.trim() || null,
    };

    if (editingSymbol) {
      updateMut.mutate({ symbol: editingSymbol, updates: payload });
    } else {
      createMut.mutate(payload);
    }
  }

  function updateField(field: keyof FormData, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  if (isLoading) return <LoadingSpinner />;

  if (error) {
    return (
      <div className="text-danger text-sm">
        Error loading instruments: {(error as Error).message}
      </div>
    );
  }

  const instruments = data?.instruments ?? [];

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-text-primary">Instruments</h1>
          <span className="text-xs font-mono text-text-muted bg-surface-2 px-2 py-0.5 rounded-full">
            {instruments.length}
          </span>
        </div>
        <button
          onClick={startCreate}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-accent hover:bg-accent-hover text-white rounded-lg transition-all hover:shadow-glow-accent"
        >
          <Plus size={14} />
          New
        </button>
      </div>

      {(createMut.isError || updateMut.isError) && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-danger/10 border border-danger/20 text-sm text-danger animate-fade-in">
          Error: {((createMut.error || updateMut.error) as Error).message}
        </div>
      )}

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="card p-5 space-y-4 animate-slide-in"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary">
              {editingSymbol ? `Edit ${editingSymbol}` : 'New Instrument'}
            </h2>
            <button type="button" onClick={resetForm} className="text-text-muted hover:text-text-primary transition-colors">
              <X size={16} />
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-[10px] text-text-muted uppercase tracking-widest mb-1.5">Symbol</label>
              <input
                type="text"
                value={form.symbol}
                onChange={(e) => updateField('symbol', e.target.value)}
                required
                disabled={!!editingSymbol}
                className="w-full px-3 py-2 text-sm bg-surface-2 border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent/50 focus:ring-1 focus:ring-accent/30 focus:outline-none disabled:opacity-50 transition-all font-mono"
                placeholder="ES"
              />
            </div>
            <div>
              <label className="block text-[10px] text-text-muted uppercase tracking-widest mb-1.5">Type</label>
              <select
                value={form.sec_type}
                onChange={(e) => updateField('sec_type', e.target.value)}
                className="w-full px-3 py-2 text-sm bg-surface-2 border border-border rounded-lg text-text-primary focus:border-accent/50 focus:ring-1 focus:ring-accent/30 focus:outline-none transition-all"
              >
                {SEC_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[10px] text-text-muted uppercase tracking-widest mb-1.5">Exchange</label>
              <input
                type="text"
                value={form.exchange}
                onChange={(e) => updateField('exchange', e.target.value)}
                required
                className="w-full px-3 py-2 text-sm bg-surface-2 border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent/50 focus:ring-1 focus:ring-accent/30 focus:outline-none transition-all font-mono"
                placeholder="CME"
              />
            </div>
            <div>
              <label className="block text-[10px] text-text-muted uppercase tracking-widest mb-1.5">Currency</label>
              <input
                type="text"
                value={form.currency}
                onChange={(e) => updateField('currency', e.target.value)}
                required
                className="w-full px-3 py-2 text-sm bg-surface-2 border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent/50 focus:ring-1 focus:ring-accent/30 focus:outline-none transition-all font-mono"
                placeholder="USD"
              />
            </div>
            <div>
              <label className="block text-[10px] text-text-muted uppercase tracking-widest mb-1.5">Multiplier</label>
              <input
                type="number"
                step="any"
                value={form.multiplier}
                onChange={(e) => updateField('multiplier', e.target.value)}
                required
                className="w-full px-3 py-2 text-sm bg-surface-2 border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent/50 focus:ring-1 focus:ring-accent/30 focus:outline-none transition-all font-mono"
              />
            </div>
            <div>
              <label className="block text-[10px] text-text-muted uppercase tracking-widest mb-1.5">Min Tick</label>
              <input
                type="number"
                step="any"
                value={form.min_tick}
                onChange={(e) => updateField('min_tick', e.target.value)}
                required
                className="w-full px-3 py-2 text-sm bg-surface-2 border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent/50 focus:ring-1 focus:ring-accent/30 focus:outline-none transition-all font-mono"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-[10px] text-text-muted uppercase tracking-widest mb-1.5">Description</label>
              <input
                type="text"
                value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
                className="w-full px-3 py-2 text-sm bg-surface-2 border border-border rounded-lg text-text-primary placeholder-text-muted focus:border-accent/50 focus:ring-1 focus:ring-accent/30 focus:outline-none transition-all"
                placeholder="E-mini S&P 500"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button
              type="button"
              onClick={resetForm}
              className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary bg-surface-2 hover:bg-surface-3 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 text-sm bg-accent hover:bg-accent-hover text-white rounded-lg transition-all hover:shadow-glow-accent"
            >
              {editingSymbol ? 'Save' : 'Create'}
            </button>
          </div>
        </form>
      )}

      {instruments.length === 0 && !showForm && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Package size={48} className="text-text-muted mb-3" />
          <p className="text-sm text-text-muted">No instruments registered</p>
        </div>
      )}

      {instruments.length > 0 && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2/50">
                  <th className="py-3 px-4 text-left text-[10px] font-semibold text-text-muted uppercase tracking-widest">Symbol</th>
                  <th className="py-3 px-4 text-left text-[10px] font-semibold text-text-muted uppercase tracking-widest">Type</th>
                  <th className="py-3 px-4 text-left text-[10px] font-semibold text-text-muted uppercase tracking-widest">Exchange</th>
                  <th className="py-3 px-4 text-left text-[10px] font-semibold text-text-muted uppercase tracking-widest">Currency</th>
                  <th className="py-3 px-4 text-right text-[10px] font-semibold text-text-muted uppercase tracking-widest">Mult.</th>
                  <th className="py-3 px-4 text-right text-[10px] font-semibold text-text-muted uppercase tracking-widest">Tick</th>
                  <th className="py-3 px-4 text-left text-[10px] font-semibold text-text-muted uppercase tracking-widest">Description</th>
                  <th className="py-3 px-4 w-20"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {instruments.map((inst) => (
                  <tr
                    key={inst.id}
                    className="group hover:bg-surface-2/30 transition-colors"
                  >
                    <td className="py-2.5 px-4">
                      <span className="font-mono font-semibold text-text-primary">{inst.symbol}</span>
                    </td>
                    <td className="py-2.5 px-4">
                      <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-medium border ${secTypeBadge[inst.sec_type] || secTypeBadge.FUT}`}>
                        {inst.sec_type}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-text-secondary font-mono text-xs">{inst.exchange}</td>
                    <td className="py-2.5 px-4 text-text-muted text-xs">{inst.currency}</td>
                    <td className="py-2.5 px-4 text-text-secondary text-right font-mono">{inst.multiplier.toLocaleString()}</td>
                    <td className="py-2.5 px-4 text-text-secondary text-right font-mono">{inst.min_tick}</td>
                    <td className="py-2.5 px-4 text-text-muted text-xs">{inst.description ?? '-'}</td>
                    <td className="py-2.5 px-4">
                      <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => startEdit(inst)}
                          className="p-1.5 rounded-md text-text-muted hover:text-accent hover:bg-accent/10 transition-colors"
                          title="Edit"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => setConfirmDelete(inst.symbol)}
                          className="p-1.5 rounded-md text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Delete instrument"
        message={`Are you sure you want to delete the instrument "${confirmDelete}"?`}
        confirmLabel="Delete"
        onConfirm={() => {
          if (confirmDelete) {
            deleteMut.mutate(confirmDelete);
          }
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
