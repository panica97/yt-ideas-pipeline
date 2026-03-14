import TodoHighlight from './TodoHighlight';

interface Condition {
  type?: string;
  code?: string;
  description?: string;
  [key: string]: unknown;
}

interface ConditionListProps {
  conditions: Condition[];
  todoFields?: string[];
  basePath?: string;
}

function isTodo(value: unknown): boolean {
  return typeof value === 'string' && value === '_TODO';
}

export default function ConditionList({ conditions, todoFields = [], basePath = '' }: ConditionListProps) {
  if (!conditions || conditions.length === 0) {
    return <p className="text-xs text-slate-500">Sin condiciones definidas</p>;
  }

  return (
    <ul className="space-y-1.5">
      {conditions.map((cond, i) => {
        const condPath = basePath ? `${basePath}.${i}` : `${i}`;
        const typeIsTodo = isTodo(cond.type) || todoFields.some((f) => f.includes(`${condPath}.type`));
        const codeIsTodo = isTodo(cond.code) || todoFields.some((f) => f.includes(`${condPath}.code`));

        return (
          <li key={i} className="text-xs bg-slate-700/30 rounded px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-slate-500 font-medium">
                {typeIsTodo ? <TodoHighlight>_TODO</TodoHighlight> : (cond.type || 'condition')}:
              </span>
              <span className="text-slate-300">
                {codeIsTodo ? <TodoHighlight>_TODO</TodoHighlight> : (cond.code || cond.description || JSON.stringify(cond))}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
