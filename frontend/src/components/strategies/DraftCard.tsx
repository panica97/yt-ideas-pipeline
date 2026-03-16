import { useState, useRef, useCallback } from 'react';
import type { DraftDetail } from '../../types/draft';

interface DraftCardProps {
  draft: DraftDetail;
}

function StatusTag({ label, active }: { label: string; active: boolean }) {
  return (
    <span
      className={`text-xs px-1.5 py-0.5 rounded ${
        active
          ? 'bg-green-500/20 text-green-400 border border-green-500/30'
          : 'bg-slate-700/50 text-slate-500 border border-slate-600'
      }`}
    >
      {label}
    </span>
  );
}

export default function DraftCard({ draft }: DraftCardProps) {
  const [expanded, setExpanded] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  const scrollToField = useCallback((field: string) => {
    const pre = preRef.current;
    if (!pre) return;
    // Build regex: the field path's last segment is the JSON key with "_TODO" value
    const lastKey = field.split('.').pop() ?? field;
    const regex = new RegExp(`"${lastKey}"\\s*:\\s*"_TODO"`);
    const text = pre.textContent ?? '';
    const match = regex.exec(text);
    if (!match) return;

    // Find the text node and character offset
    const walker = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
    let charCount = 0;
    while (walker.nextNode()) {
      const node = walker.currentNode as Text;
      const nodeLen = node.length;
      if (charCount + nodeLen > match.index) {
        // Create a temporary range to get position
        const range = document.createRange();
        range.setStart(node, match.index - charCount);
        range.setEnd(node, Math.min(match.index - charCount + match[0].length, nodeLen));
        const rect = range.getBoundingClientRect();
        const preRect = pre.getBoundingClientRect();
        // Scroll the pre element so the match is visible
        pre.scrollTop = pre.scrollTop + rect.top - preRect.top - preRect.height / 3;

        // Flash highlight
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
  }, []);

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      {/* Collapsed header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 text-left hover:bg-slate-700/30 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-semibold text-white truncate">{draft.strat_name}</span>
          <span className="text-xs font-mono text-slate-500 bg-slate-700/50 px-1.5 py-0.5 rounded shrink-0">
            {draft.strat_code}
          </span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded shrink-0 ${
              draft.todo_count > 0
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                : 'bg-green-500/20 text-green-400 border border-green-500/30'
            }`}
          >
            {draft.todo_count > 0 ? `${draft.todo_count} TODOs` : 'Completo'}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <StatusTag label="active" active={draft.active} />
          <StatusTag label="tested" active={draft.tested} />
          <StatusTag label="prod" active={draft.prod} />
          <span className="text-slate-500 text-xs ml-1">{expanded ? '\u25B2' : '\u25BC'}</span>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-slate-700 p-3 space-y-3">
          {/* TODO fields list */}
          {draft.todo_fields && draft.todo_fields.length > 0 && (
            <div>
              <h5 className="text-xs font-semibold text-amber-400 uppercase mb-1">Campos pendientes</h5>
              <ul className="space-y-0.5">
                {draft.todo_fields.map((field, i) => (
                  <li
                    key={i}
                    onClick={() => scrollToField(field)}
                    className="text-xs text-amber-300/80 font-mono bg-amber-500/10 rounded px-2 py-1 cursor-pointer hover:bg-amber-500/20 hover:text-amber-200 transition-colors"
                  >
                    {field}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Full data JSON */}
          {draft.data && (
            <div>
              <h5 className="text-xs font-semibold text-slate-400 uppercase mb-1">Datos completos</h5>
              <pre ref={preRef} className="text-xs text-slate-300 bg-slate-900/50 rounded p-3 overflow-x-auto max-h-80 overflow-y-auto">
                {JSON.stringify(draft.data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
