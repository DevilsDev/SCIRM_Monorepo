import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { getThemeColors } from './theme';

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  type: string;
  label: string;
  risk_score?: number;
  risk_tier?: string;
  severity?: string;
}

interface GraphEdge {
  source: string;
  target: string;
  relationship: string;
}

const NODE_COLORS: Record<string, string> = {
  organization: '#3b82f6',
  supplier: '#22c55e',
  risk: '#ef4444',
};

const NODE_RADIUS: Record<string, number> = {
  organization: 28,
  supplier: 20,
  risk: 16,
};

interface ForceGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  height?: number;
}

export default function ForceGraph({ nodes: rawNodes, edges: rawEdges, height = 500 }: ForceGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !rawNodes.length) return;

    const container = containerRef.current;
    const width = container.clientWidth;

    d3.select(container).selectAll('*').remove();
    const colors = getThemeColors();

    const svg = d3.select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    // Defs for arrow markers
    svg.append('defs').append('marker')
      .attr('id', 'arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 30)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#d1d5db');

    const g = svg.append('g');

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 4])
      .on('zoom', (event) => g.attr('transform', event.transform));
    svg.call(zoom);

    // Deep copy nodes and edges for D3 mutation
    const nodes: GraphNode[] = rawNodes.map((n) => ({ ...n }));
    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = rawEdges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e) => ({ ...e }));

    // Force simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id((d: any) => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d: any) => (NODE_RADIUS[d.type] || 16) + 10));

    // Links
    const link = g.selectAll('.link')
      .data(edges)
      .enter()
      .append('line')
      .attr('class', 'link')
      .attr('stroke', '#d1d5db')
      .attr('stroke-width', 1.5)
      .attr('marker-end', 'url(#arrow)');

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'fixed pointer-events-none bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl opacity-0 transition-opacity z-50 max-w-xs');

    // Node groups
    const node = g.selectAll('.node')
      .data(nodes)
      .enter()
      .append('g')
      .attr('class', 'node')
      .style('cursor', 'grab')
      .call(d3.drag<SVGGElement, GraphNode>()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }) as any);

    // Node circles with animated entry
    node.append('circle')
      .attr('r', 0)
      .attr('fill', (d) => NODE_COLORS[d.type] || '#94a3b8')
      .attr('stroke', colors.stroke)
      .attr('stroke-width', 2.5)
      .transition()
      .duration(600)
      .delay((_, i) => i * 30)
      .ease(d3.easeBackOut)
      .attr('r', (d) => NODE_RADIUS[d.type] || 16);

    // Node labels
    node.append('text')
      .attr('dy', (d) => (NODE_RADIUS[d.type] || 16) + 14)
      .attr('text-anchor', 'middle')
      .attr('class', 'text-[10px] font-medium')
      .attr('fill', colors.textLight)
      .text((d) => d.label.length > 18 ? d.label.slice(0, 16) + '...' : d.label);

    // Node type icon (first letter)
    node.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('class', 'font-bold')
      .attr('fill', 'white')
      .attr('font-size', (d) => `${(NODE_RADIUS[d.type] || 16) * 0.7}px`)
      .text((d) => d.type === 'organization' ? 'O' : d.type === 'supplier' ? 'S' : 'R');

    // Hover effects
    node.on('mouseover', function (event, d) {
      d3.select(this).select('circle').transition().duration(150).attr('r', (NODE_RADIUS[d.type] || 16) * 1.3);
      let html = `<strong>${d.label}</strong><br/>Type: ${d.type}`;
      if (d.risk_score != null) html += `<br/>Risk: ${d.risk_score}/100`;
      if (d.risk_tier) html += `<br/>Tier: ${d.risk_tier}`;
      if (d.severity) html += `<br/>Severity: ${d.severity}`;
      tooltip.style('opacity', '1').html(html)
        .style('left', `${event.pageX + 14}px`).style('top', `${event.pageY - 30}px`);
    })
    .on('mousemove', function (event) {
      tooltip.style('left', `${event.pageX + 14}px`).style('top', `${event.pageY - 30}px`);
    })
    .on('mouseout', function (_, d) {
      d3.select(this).select('circle').transition().duration(150).attr('r', NODE_RADIUS[d.type] || 16);
      tooltip.style('opacity', '0');
    });

    // Tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      node.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
      tooltip.remove();
    };
  }, [rawNodes, rawEdges, height]);

  if (!rawNodes.length) {
    return <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height }}>No supply chain data</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
}
