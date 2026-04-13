import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Recommendation } from '../services/api';

const PRIORITY_COLORS: Record<string, string> = {
  high: '#ef4444',
  medium: '#eab308',
  low: '#22c55e',
};

interface PriorityMatrixProps {
  recommendations: Recommendation[];
}

export default function PriorityMatrix({ recommendations }: PriorityMatrixProps) {
  const data = recommendations
    .filter((r) => r.estimated_cost != null)
    .map((r) => ({
      x: r.estimated_cost!,
      y: r.estimated_impact,
      name: r.title,
      priority: r.priority,
    }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
        No recommendation data to display
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 20 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          type="number"
          dataKey="x"
          name="Cost"
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          label={{ value: 'Estimated Cost', position: 'bottom', offset: 0 }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name="Impact"
          domain={[0, 10]}
          label={{ value: 'Impact', angle: -90, position: 'insideLeft' }}
        />
        <Tooltip
          formatter={(value: number, name: string) =>
            name === 'Cost' ? `$${value.toLocaleString()}` : value.toFixed(1)
          }
          labelFormatter={() => ''}
          content={({ payload }) => {
            if (!payload?.length) return null;
            const d = payload[0].payload;
            return (
              <div className="bg-white shadow-lg rounded-lg p-2 border text-xs">
                <p className="font-medium">{d.name}</p>
                <p>Cost: ${d.x.toLocaleString()}</p>
                <p>Impact: {d.y.toFixed(1)}</p>
              </div>
            );
          }}
        />
        <Scatter data={data}>
          {data.map((entry, i) => (
            <Cell key={i} fill={PRIORITY_COLORS[entry.priority] || '#94a3b8'} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}
