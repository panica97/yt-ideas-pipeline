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
      <div className="text-red-400 text-sm">
        Error al cargar instrumentos: {(error as Error).message}
      </div>
    );
  }

  const instruments = data?.instruments ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Instrumentos</h1>
        <button
          onClick={startCreate}
          className="px-3 py-1.5 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded transition-colors"
        >
          + Nuevo
        </button>
      </div>

      {(createMut.isError || updateMut.isError) && (
        <p className="text-sm text-red-400">
          Error: {((createMut.error || updateMut.error) as Error).message}
        </p>
      )}

      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3"
        >
          <h2 className="text-sm font-semibold text-white">
            {editingSymbol ? `Editar ${editingSymbol}` : 'Nuevo instrumento'}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Symbol</label>
              <input
                type="text"
                value={form.symbol}
                onChange={(e) => updateField('symbol', e.target.value)}
                required
                disabled={!!editingSymbol}
                className="w-full px-2 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white placeholder-slate-500 focus:border-primary-500 focus:outline-none disabled:opacity-50"
                placeholder="ES"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Tipo</label>
              <select
                value={form.sec_type}
                onChange={(e) => updateField('sec_type', e.target.value)}
                className="w-full px-2 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white focus:border-primary-500 focus:outline-none"
              >
                {SEC_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Exchange</label>
              <input
                type="text"
                value={form.exchange}
                onChange={(e) => updateField('exchange', e.target.value)}
                required
                className="w-full px-2 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white placeholder-slate-500 focus:border-primary-500 focus:outline-none"
                placeholder="CME"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Moneda</label>
              <input
                type="text"
                value={form.currency}
                onChange={(e) => updateField('currency', e.target.value)}
                required
                className="w-full px-2 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white placeholder-slate-500 focus:border-primary-500 focus:outline-none"
                placeholder="USD"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Multiplicador</label>
              <input
                type="number"
                step="any"
                value={form.multiplier}
                onChange={(e) => updateField('multiplier', e.target.value)}
                required
                className="w-full px-2 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white placeholder-slate-500 focus:border-primary-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Min Tick</label>
              <input
                type="number"
                step="any"
                value={form.min_tick}
                onChange={(e) => updateField('min_tick', e.target.value)}
                required
                className="w-full px-2 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white placeholder-slate-500 focus:border-primary-500 focus:outline-none"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs text-slate-400 mb-1">Descripcion</label>
              <input
                type="text"
                value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
                className="w-full px-2 py-1.5 text-sm bg-slate-900 border border-slate-600 rounded text-white placeholder-slate-500 focus:border-primary-500 focus:outline-none"
                placeholder="E-mini S&P 500"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={resetForm}
              className="px-3 py-1.5 text-sm text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 rounded transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="px-3 py-1.5 text-sm bg-primary-600 hover:bg-primary-700 text-white rounded transition-colors"
            >
              {editingSymbol ? 'Guardar' : 'Crear'}
            </button>
          </div>
        </form>
      )}

      {instruments.length === 0 && !showForm && (
        <p className="text-sm text-slate-500">No hay instrumentos registrados.</p>
      )}

      {instruments.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400">
                <th className="py-2 px-3 font-medium">Symbol</th>
                <th className="py-2 px-3 font-medium">Tipo</th>
                <th className="py-2 px-3 font-medium">Exchange</th>
                <th className="py-2 px-3 font-medium">Moneda</th>
                <th className="py-2 px-3 font-medium text-right">Multiplicador</th>
                <th className="py-2 px-3 font-medium text-right">Min Tick</th>
                <th className="py-2 px-3 font-medium">Descripcion</th>
                <th className="py-2 px-3 font-medium text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {instruments.map((inst) => (
                <tr
                  key={inst.id}
                  className="border-b border-slate-700/50 hover:bg-slate-800/50 transition-colors"
                >
                  <td className="py-2 px-3 text-white font-mono">{inst.symbol}</td>
                  <td className="py-2 px-3 text-slate-300">{inst.sec_type}</td>
                  <td className="py-2 px-3 text-slate-300">{inst.exchange}</td>
                  <td className="py-2 px-3 text-slate-300">{inst.currency}</td>
                  <td className="py-2 px-3 text-slate-300 text-right">{inst.multiplier}</td>
                  <td className="py-2 px-3 text-slate-300 text-right">{inst.min_tick}</td>
                  <td className="py-2 px-3 text-slate-400">{inst.description ?? '-'}</td>
                  <td className="py-2 px-3 text-right">
                    <button
                      onClick={() => startEdit(inst)}
                      className="text-xs text-primary-400 hover:text-primary-300 mr-3 transition-colors"
                    >
                      Editar
                    </button>
                    <button
                      onClick={() => setConfirmDelete(inst.symbol)}
                      className="text-xs text-red-400 hover:text-red-300 transition-colors"
                    >
                      Borrar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Eliminar instrumento"
        message={`Seguro que quieres eliminar el instrumento "${confirmDelete}"?`}
        confirmLabel="Eliminar"
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
