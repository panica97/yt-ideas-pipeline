import type { DraftData } from '../../../types/draft-data';
import { getIndicatorCategory, getIndicatorColors } from '../draft-utils';

interface Props {
  data: DraftData;
  todoFields: string[];
}

export default function IndicatorsSection({ data }: Props) {
  const timeframes = Object.keys(data.ind_list);

  if (timeframes.length === 0) {
    return <p className="text-sm text-text-muted italic">Sin indicadores definidos</p>;
  }

  return (
    <div className="space-y-3">
      {timeframes.map(tf => (
        <div key={tf}>
          <div className="text-xs font-medium text-text-muted uppercase mb-2 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-indigo-400" />
            {tf}
          </div>
          <div className="flex flex-wrap gap-2">
            {data.ind_list[tf].map((ind, i) => {
              const cat = getIndicatorCategory(ind.indicator);
              const colors = getIndicatorColors(cat);
              const params = Object.entries(ind.params)
                .filter(([k]) => k !== 'indCode')
                .map(([k, v]) => `${k}=${v}`)
                .join(', ');

              return (
                <div
                  key={i}
                  className={`inline-flex flex-col px-2.5 py-1.5 rounded-lg border ${colors}`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold">{ind.indicator}</span>
                    <span className="text-[10px] font-mono opacity-70">{ind.params.indCode}</span>
                  </div>
                  {params && (
                    <span className="text-[10px] opacity-60 mt-0.5">{params}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
