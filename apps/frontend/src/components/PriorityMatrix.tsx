import ScatterQuadrant from './d3/ScatterQuadrant';
import { Recommendation } from '../services/api';

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

  return <ScatterQuadrant data={data} />;
}
