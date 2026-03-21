import { useState, useCallback, useRef } from 'react';
import type { DraftDetail } from '../../types/draft';
import { parseDraftData, getTodoFieldsForSection, humanizeFieldPath } from './draft-utils';
import SectionPanel from './draft-sections/SectionPanel';
import InstrumentSection from './draft-sections/InstrumentSection';
import IndicatorsSection from './draft-sections/IndicatorsSection';
import ConditionsSection from './draft-sections/ConditionsSection';
import NotesSection from './draft-sections/NotesSection';

interface DraftViewerProps {
  draft: DraftDetail;
}

export default function DraftViewer({ draft }: DraftViewerProps) {
  const [showJson, setShowJson] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  const parsed = parseDraftData(draft.data);
  const todoFields = draft.todo_fields ?? [];

  const scrollToFieldInJson = useCallback((field: string) => {
    // Open JSON if not visible
    if (!showJson) setShowJson(true);

    // Wait for the <pre> to render, then find and highlight the field
    setTimeout(() => {
      const pre = preRef.current;
      if (!pre) return;

      const lastKey = field.split('.').pop() ?? field;
      const regex = new RegExp(`"${lastKey}"\\s*:\\s*"_TODO"`);
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
          mark.className = 'bg-amber-400/30 text-amber-200 rounded';
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
    }, 50);
  }, [showJson]);

  // If parsing fails, show JSON fallback directly
  if (!parsed) {
    return (
      <div>
        <p className="text-xs text-slate-500 italic mb-2">No se pudo interpretar la estructura del draft</p>
        <pre className="text-xs text-slate-300 bg-slate-900/50 rounded p-3 overflow-x-auto max-h-80 overflow-y-auto">
          {JSON.stringify(draft.data, null, 2)}
        </pre>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Visual sections */}
      <div className="space-y-2">
        <SectionPanel id="instrument" title="Instrumento" icon={'\uD83D\uDCCA'} defaultOpen>
          <InstrumentSection data={parsed} todoFields={getTodoFieldsForSection(todoFields, 'instrument')} />
        </SectionPanel>

        <SectionPanel id="indicators" title="Indicadores" icon={'\uD83D\uDCC8'} defaultOpen>
          <IndicatorsSection data={parsed} todoFields={getTodoFieldsForSection(todoFields, 'indicators')} />
        </SectionPanel>

        <SectionPanel id="conditions" title="Entradas" icon={'\u2699\uFE0F'}>
          <ConditionsSection data={parsed} todoFields={getTodoFieldsForSection(todoFields, 'conditions')} sectionType="entry" />
        </SectionPanel>

        {parsed.exit_conds.length > 0 && (
          <SectionPanel id="exit" title="Salida" icon={'\uD83D\uDEAA'}>
            <ConditionsSection data={parsed} todoFields={getTodoFieldsForSection(todoFields, 'conditions')} sectionType="exit" />
          </SectionPanel>
        )}

        {parsed._notes && Object.keys(parsed._notes).length > 0 && (
          <SectionPanel id="notes" title="Notas" icon={'\uD83D\uDCDD'}>
            <NotesSection notes={parsed._notes} />
          </SectionPanel>
        )}
      </div>

      {/* TODO fields — at the bottom, click opens JSON and highlights */}
      {todoFields.length > 0 && (
        <div>
          <h5 className="text-xs font-semibold text-amber-400 uppercase mb-1">Campos pendientes</h5>
          <ul className="space-y-0.5">
            {todoFields.map((field, i) => (
              <li
                key={i}
                onClick={() => scrollToFieldInJson(field)}
                className="text-xs text-amber-300/80 font-mono bg-amber-500/10 rounded px-2 py-1 cursor-pointer hover:bg-amber-500/20 hover:text-amber-200 transition-colors"
              >
                {humanizeFieldPath(field, parsed)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* JSON fallback toggle */}
      <div>
        <button
          onClick={() => setShowJson(!showJson)}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors underline"
        >
          {showJson ? 'Ocultar JSON' : 'Ver JSON'}
        </button>
        {showJson && (
          <pre ref={preRef} className="mt-2 text-xs text-slate-300 bg-slate-900/50 rounded p-3 overflow-x-auto max-h-80 overflow-y-auto">
            {JSON.stringify(draft.data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
