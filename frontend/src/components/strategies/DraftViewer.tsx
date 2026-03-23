import { useState, useCallback, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import type { DraftDetail } from '../../types/draft';
import type { Instrument } from '../../types/instrument';
import { parseDraftData, getTodoFieldsForSection, humanizeFieldPath } from './draft-utils';
import { updateDraftData } from '../../services/strategies';
import { getInstruments } from '../../services/instruments';
import SectionPanel from './draft-sections/SectionPanel';
import InstrumentSection from './draft-sections/InstrumentSection';
import IndicatorsSection from './draft-sections/IndicatorsSection';
import ConditionsSection from './draft-sections/ConditionsSection';
import NotesSection from './draft-sections/NotesSection';
import BacktestPanel from './BacktestPanel';

const INSTRUMENT_FIELD_MAP = {
  symbol: 'symbol',
  sec_type: 'secType',
  exchange: 'exchange',
  currency: 'currency',
  multiplier: 'multiplier',
  min_tick: 'minTick',
} as const;

interface DraftViewerProps {
  draft: DraftDetail;
}

export default function DraftViewer({ draft }: DraftViewerProps) {
  const [showJson, setShowJson] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const queryClient = useQueryClient();

  const { data: instrumentsData } = useQuery({
    queryKey: ['instruments'],
    queryFn: async () => {
      const res = await getInstruments();
      return res.instruments;
    },
    staleTime: Infinity,
  });

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      updateDraftData(draft.strat_code, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['draft', draft.strat_code] });
      queryClient.invalidateQueries({ queryKey: ['drafts'] });
      queryClient.invalidateQueries({ queryKey: ['drafts-by-strategy'] });
      setEditMode(false);
      setJsonError(null);
    },
    onError: (error: AxiosError<{ detail: string | { errors: string[]; message: string } }>) => {
      const detail = error.response?.data?.detail;
      if (typeof detail === 'object' && detail?.errors) {
        setJsonError(detail.errors.join('\n'));
      } else if (typeof detail === 'string') {
        setJsonError(detail);
      } else {
        setJsonError('Error saving changes');
      }
    },
  });

  const handleEditJson = () => {
    setJsonText(JSON.stringify(draft.data, null, 2));
    setJsonError(null);
    setEditMode(true);
  };

  const handleSaveJson = () => {
    try {
      const parsed = JSON.parse(jsonText);
      setJsonError(null);
      mutation.mutate(parsed);
    } catch (e) {
      setJsonError(`Invalid JSON: ${(e as Error).message}`);
    }
  };

  const handleCancelEdit = () => {
    setEditMode(false);
    setJsonError(null);
  };

  const handleSymbolChange = useCallback((instrument: Instrument) => {
    if (instrument.symbol === draft.data?.symbol) return;

    const mappedFields: Record<string, unknown> = {};
    for (const [instKey, draftKey] of Object.entries(INSTRUMENT_FIELD_MAP)) {
      mappedFields[draftKey] = instrument[instKey as keyof Instrument];
    }

    const mergedData = { ...draft.data, ...mappedFields };
    mutation.mutate(mergedData);
  }, [draft.data, mutation]);

  const parsed = parseDraftData(draft.data);
  const todoFields = draft.todo_fields ?? [];

  const scrollToFieldInJson = useCallback((field: string) => {
    // Open JSON if not visible
    if (!showJson) setShowJson(true);

    const lastKey = field.split('.').pop() ?? field;
    // Match both exact "_TODO" and embedded "_TODO" within strings
    const regex = new RegExp(`"${lastKey}"\\s*:\\s*"[^"]*_TODO[^"]*"`);

    // Wait for the element to render, then find and highlight the field
    setTimeout(() => {
      if (editMode) {
        // Edit mode: select the match inside the textarea
        const ta = textareaRef.current;
        if (!ta) return;

        const match = regex.exec(jsonText);
        if (!match) return;

        ta.focus();
        ta.selectionStart = match.index;
        ta.selectionEnd = match.index + match[0].length;

        // Scroll textarea so the selection is visible
        // Estimate line position: count newlines before match
        const textBefore = jsonText.slice(0, match.index);
        const linesBefore = textBefore.split('\n').length;
        const lineHeight = 16; // approximate line height in px for text-xs mono
        ta.scrollTop = Math.max(0, linesBefore * lineHeight - ta.clientHeight / 3);
      } else {
        // View mode: highlight inside the <pre>
        const pre = preRef.current;
        if (!pre) return;

        const text = pre.textContent ?? '';
        const match = regex.exec(text);
        if (!match) return;

        const walker = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
        let charCount = 0;
        while (walker.nextNode()) {
          const node = walker.currentNode as Text;
          const nodeLen = node.length;
          if (charCount + nodeLen > match.index) {
            const range = document.createRange();
            range.setStart(node, match.index - charCount);
            range.setEnd(node, Math.min(match.index - charCount + match[0].length, nodeLen));
            const rect = range.getBoundingClientRect();
            const preRect = pre.getBoundingClientRect();
            pre.scrollTop = pre.scrollTop + rect.top - preRect.top - preRect.height / 3;

            const mark = document.createElement('mark');
            mark.className = 'bg-warn/30 text-warn rounded px-0.5';
            range.surroundContents(mark);
            setTimeout(() => {
              const parent = mark.parentNode;
              if (parent) {
                parent.replaceChild(document.createTextNode(mark.textContent ?? ''), mark);
                parent.normalize();
              }
            }, 1500);
            break;
          }
          charCount += nodeLen;
        }
      }
    }, 50);
  }, [showJson, editMode, jsonText]);

  // If parsing fails, show JSON fallback directly
  if (!parsed) {
    return (
      <div>
        <p className="text-xs text-text-muted italic mb-2">Could not parse the draft structure</p>
        <pre className="text-xs text-text-secondary bg-surface-0/50 rounded p-3 overflow-x-auto max-h-80 overflow-y-auto">
          {JSON.stringify(draft.data, null, 2)}
        </pre>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Visual sections */}
      <div className="space-y-2">
        <SectionPanel id="instrument" title="Instrument" icon={'\uD83D\uDCCA'} defaultOpen>
          <InstrumentSection data={parsed} todoFields={getTodoFieldsForSection(todoFields, 'instrument')} instruments={instrumentsData} onSymbolChange={handleSymbolChange} isMutating={mutation.isPending} />
        </SectionPanel>

        <SectionPanel id="indicators" title="Indicators" icon={'\uD83D\uDCC8'} defaultOpen>
          <IndicatorsSection data={parsed} todoFields={getTodoFieldsForSection(todoFields, 'indicators')} />
        </SectionPanel>

        <SectionPanel id="conditions" title="Entries" icon={'\u2699\uFE0F'}>
          <ConditionsSection data={parsed} todoFields={getTodoFieldsForSection(todoFields, 'conditions')} sectionType="entry" />
        </SectionPanel>

        {parsed.exit_conds.length > 0 && (
          <SectionPanel id="exit" title="Exit" icon={'\uD83D\uDEAA'}>
            <ConditionsSection data={parsed} todoFields={getTodoFieldsForSection(todoFields, 'conditions')} sectionType="exit" />
          </SectionPanel>
        )}

        {parsed._notes && Object.keys(parsed._notes).length > 0 && (
          <SectionPanel id="notes" title="Notes" icon={'\uD83D\uDCDD'}>
            <NotesSection notes={parsed._notes} />
          </SectionPanel>
        )}

        <SectionPanel id="backtest" title="Backtest" icon={'\uD83E\uDDEA'}>
          <BacktestPanel
            stratCode={draft.strat_code}
            backtestable={draft.todo_count === 0}
            defaultSymbol={parsed?.symbol}
            primaryTimeframe={parsed?.control_params?.primary_timeframe}
          />
        </SectionPanel>
      </div>

      {/* TODO fields — at the bottom, click opens JSON and highlights */}
      {todoFields.length > 0 && (
        <div>
          <h5 className="text-xs font-semibold text-warn uppercase mb-1">Pending Fields</h5>
          <ul className="space-y-0.5">
            {todoFields.map((field, i) => (
              <li
                key={i}
                onClick={() => scrollToFieldInJson(field)}
                className="text-xs text-warn font-mono bg-warn/10 border border-warn/20 rounded px-2 py-1 cursor-pointer hover:bg-warn/20 hover:border-warn/30 transition-colors"
              >
                {humanizeFieldPath(field, parsed)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* JSON view / edit toggle */}
      <div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowJson(!showJson)}
            className="text-xs text-text-muted hover:text-text-secondary transition-colors underline"
          >
            {showJson ? 'Hide JSON' : 'View JSON'}
          </button>
          {!editMode && (
            <button
              onClick={handleEditJson}
              className="text-xs text-accent hover:text-accent/80 transition-colors underline"
            >
              Edit JSON
            </button>
          )}
        </div>

        {editMode ? (
          <div className="mt-2 space-y-2">
            <textarea
              ref={textareaRef}
              value={jsonText}
              onChange={(e) => setJsonText(e.target.value)}
              className="w-full font-mono text-xs bg-surface-2 text-text-primary border border-border rounded p-3 resize-y focus:outline-none focus:ring-1 focus:ring-accent"
              style={{ minHeight: '400px' }}
              spellCheck={false}
            />
            {jsonError && (
              <p className="text-xs text-danger bg-danger/10 border border-danger/20 rounded px-2 py-1 whitespace-pre-wrap">
                {jsonError}
              </p>
            )}
            <div className="flex gap-2">
              <button
                onClick={handleSaveJson}
                disabled={mutation.isPending}
                className="text-xs px-3 py-1 bg-accent text-surface-0 rounded hover:bg-accent/90 transition-colors disabled:opacity-50"
              >
                {mutation.isPending ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={handleCancelEdit}
                disabled={mutation.isPending}
                className="text-xs px-3 py-1 bg-surface-2 text-text-secondary border border-border rounded hover:bg-surface-3 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          showJson && (
            <pre ref={preRef} className="mt-2 text-xs text-text-secondary bg-surface-0/50 rounded p-3 overflow-x-auto max-h-80 overflow-y-auto">
              {JSON.stringify(draft.data, null, 2)}
            </pre>
          )
        )}
      </div>
    </div>
  );
}
