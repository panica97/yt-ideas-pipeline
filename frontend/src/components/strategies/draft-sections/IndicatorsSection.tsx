import type { DraftData } from '../../../types/draft-data';
import { getIndicatorCategory, getIndicatorColors } from '../draft-utils';

interface Props {
  data: DraftData;
  todoFields: string[];
}

export default function IndicatorsSection({ data }: Props) {
  const timeframes = Object.keys(data.ind_list);

  if (timeframes.length === 0) {
    return <p className="text-sm text-text-muted italic">No indicators defined</p>;
  }

  return (
    <div className="space-y-3">
      {timeframes.map(tf => (
        <div key={tf}>
          <div className="text-xs font-medium text-text-muted uppercase mb-1.5 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-indigo-400" />
            {tf}
          </div>
          <div className="border border-border rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-surface-2/50 text-text-muted">
                  <th className="text-left px-3 py-1.5 font-medium w-28">Indicator</th>
                  <th className="text-left px-3 py-1.5 font-medium w-32">Code</th>
                  <th className="text-left px-3 py-1.5 font-medium w-20">Period</th>
                  <th className="text-left px-3 py-1.5 font-medium">Parameters</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.ind_list[tf].map((ind, i) => {
                  const cat = getIndicatorCategory(ind.indicator);
                  const colors = getIndicatorColors(cat);
                  const period = ind.params.timePeriod_1;
                  const otherParams = Object.entries(ind.params)
                    .filter(([k]) => !['indCode', 'timePeriod_1'].includes(k))
                    .map(([k, v]) => `${k}=${v}`);

                  return (
                    <tr key={i} className="hover:bg-surface-2/20 transition-colors">
                      <td className="px-3 py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${colors}`}>
                          {ind.indicator}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-text-secondary">
                        {ind.params.indCode}
                      </td>
                      <td className="px-3 py-2 font-mono text-text-primary font-semibold">
                        {period ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-text-muted">
                        {otherParams.length > 0 ? (
                          <span className="font-mono">
                            {otherParams.map((p, j) => (
                              <span key={j}>
                                {j > 0 && <span className="text-border mx-1">·</span>}
                                {p}
                              </span>
                            ))}
                          </span>
                        ) : (
                          <span className="text-text-muted/50">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
