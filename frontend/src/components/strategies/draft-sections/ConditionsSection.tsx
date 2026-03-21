import type { Condition, DraftData } from '../../../types/draft-data';

interface Props {
  data: DraftData;
  todoFields: string[];
  sectionType: 'entry' | 'exit';
}

function ConditionBlock({ cond }: { cond: Condition }) {
  const displayCond = cond.cond_type === 'num_bars'
    ? `Salir tras ${cond.cond} barras`
    : cond.cond;

  return (
    <div className="flex items-start gap-2 p-2 bg-surface-1/40 rounded border border-border/50">
      <span className="text-[10px] font-mono text-text-muted mt-0.5 shrink-0">{cond.condCode}</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-text-primary font-mono">{displayCond}</div>
        <div className="flex flex-wrap gap-2 mt-1">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-2/50 text-text-muted border border-border/50">
            {cond.cond_type}
          </span>
          {cond.shift_1 != null && cond.shift_1 >= 1 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-2/50 text-text-muted">
              shift&#x2081;: {cond.shift_1}
            </span>
          )}
          {cond.shift_2 != null && cond.shift_2 >= 1 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-2/50 text-text-muted">
              shift&#x2082;: {cond.shift_2}
            </span>
          )}
          {cond.mode === 'force' && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-danger/20 text-danger border border-danger/30 font-bold">
              FORCE EXIT
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function EntryConditions({ conditions, label, bgClass }: { conditions: Condition[]; label: string; bgClass: string }) {
  if (conditions.length === 0) {
    return (
      <div className={`rounded-lg p-3 ${bgClass}`}>
        <div className="text-xs font-semibold uppercase mb-2 text-text-muted">{label}</div>
        <p className="text-xs text-text-muted italic">Sin condiciones</p>
      </div>
    );
  }

  return (
    <div className={`rounded-lg p-3 ${bgClass}`}>
      <div className="text-xs font-semibold uppercase mb-2 text-text-muted">{label}</div>
      <div className="space-y-1">
        {conditions.map((c, i) => (
          <div key={i}>
            {i > 0 && (
              <div className="text-[10px] text-center text-text-muted my-0.5">AND</div>
            )}
            <ConditionBlock cond={c} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ExitConditions({ conditions }: { conditions: Condition[] }) {
  if (conditions.length === 0) {
    return (
      <div className="rounded-lg p-3 bg-surface-2/20 border border-border/30">
        <div className="text-xs font-semibold uppercase mb-2 text-text-muted">Salida</div>
        <p className="text-xs text-text-muted italic">Sin condiciones de salida</p>
      </div>
    );
  }

  // Separate force, grouped, and singleton conditions
  const forceConditions = conditions.filter(c => c.mode === 'force');
  const normalConditions = conditions.filter(c => c.mode !== 'force');

  // Group normal conditions: those with group field go into groups, those without are singletons
  const groups = new Map<number, Condition[]>();
  const singletons: Condition[] = [];

  normalConditions.forEach(c => {
    if (c.group != null) {
      if (!groups.has(c.group)) groups.set(c.group, []);
      groups.get(c.group)!.push(c);
    } else {
      singletons.push(c);
    }
  });

  let blockIndex = 0;

  return (
    <div className="rounded-lg p-3 bg-surface-2/20 border border-border/30">
      <div className="text-xs font-semibold uppercase mb-2 text-text-muted">Salida</div>
      <div className="space-y-1">
        {/* Force conditions first */}
        {forceConditions.map((c, i) => {
          const showOr = blockIndex++ > 0;
          return (
            <div key={`force-${i}`}>
              {showOr && <div className="text-[10px] text-center text-text-muted font-bold my-1">OR</div>}
              <ConditionBlock cond={c} />
            </div>
          );
        })}

        {/* Grouped conditions */}
        {Array.from(groups.entries()).map(([, conds], gi) => {
          const showOr = blockIndex++ > 0;
          return (
            <div key={`group-${gi}`}>
              {showOr && <div className="text-[10px] text-center text-text-muted font-bold my-1">OR</div>}
              <div className="space-y-1">
                {conds.map((c, ci) => (
                  <div key={ci}>
                    {ci > 0 && <div className="text-[10px] text-center text-text-muted my-0.5">AND</div>}
                    <ConditionBlock cond={c} />
                  </div>
                ))}
              </div>
            </div>
          );
        })}

        {/* Singletons */}
        {singletons.map((c, i) => {
          const showOr = blockIndex++ > 0;
          return (
            <div key={`single-${i}`}>
              {showOr && <div className="text-[10px] text-center text-text-muted font-bold my-1">OR</div>}
              <ConditionBlock cond={c} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ConditionsSection({ data, sectionType }: Props) {
  if (sectionType === 'entry') {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <EntryConditions
            conditions={data.long_conds}
            label="Long"
            bgClass="bg-accent/5 border border-green-500/10"
          />
          <EntryConditions
            conditions={data.short_conds}
            label="Short"
            bgClass="bg-red-500/5 border border-red-500/10"
          />
        </div>
      </div>
    );
  }

  // exit
  return <ExitConditions conditions={data.exit_conds} />;
}
