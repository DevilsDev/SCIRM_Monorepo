import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { getThemeColors } from './theme';

interface ScatterPoint {
  x: number;
  y: number;
  name: string;
  priority: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  high: '#ef4444',
  medium: '#eab308',
  low: '#22c55e',
};

interface ScatterQuadrantProps {
  data: ScatterPoint[];
  height?: number;
}

export default function ScatterQuadrant({ data, height = 360 }: ScatterQuadrantProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !data.length) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const margin = { top: 30, right: 30, bottom: 50, left: 60 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    d3.select(container).selectAll('*').remove();
    const colors = getThemeColors();

    const svg = d3.select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height);

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const xMax = d3.max(data, (d) => d.x) || 100000;
    const x = d3.scaleLinear().domain([0, xMax * 1.15]).range([0, innerW]);
    const y = d3.scaleLinear().domain([0, 10]).range([innerH, 0]);

    // Grid
    g.append('g').call(d3.axisBottom(x).tickSize(innerH).tickFormat(() => '').ticks(6)).attr('stroke', colors.grid).attr('stroke-opacity', 0.3).select('.domain').remove();
    g.append('g').call(d3.axisLeft(y).tickSize(-innerW).tickFormat(() => '').ticks(5)).attr('stroke', colors.grid).attr('stroke-opacity', 0.3).select('.domain').remove();

    // Quadrant lines
    const midX = xMax * 0.5;
    const midY = 5;
    g.append('line').attr('x1', x(midX)).attr('y1', 0).attr('x2', x(midX)).attr('y2', innerH).attr('stroke', '#d1d5db').attr('stroke-dasharray', '6,4');
    g.append('line').attr('x1', 0).attr('y1', y(midY)).attr('x2', innerW).attr('y2', y(midY)).attr('stroke', '#d1d5db').attr('stroke-dasharray', '6,4');

    // Quadrant labels
    const labels = [
      { text: 'Quick Wins', x: midX * 0.5, y: 7.5, color: '#16a34a' },
      { text: 'Strategic', x: midX * 1.5, y: 7.5, color: '#2563eb' },
      { text: 'Low Priority', x: midX * 0.5, y: 2.5, color: '#9ca3af' },
      { text: 'Questionable', x: midX * 1.5, y: 2.5, color: '#dc2626' },
    ];
    labels.forEach((l) => {
      g.append('text')
        .attr('x', x(l.x)).attr('y', y(l.y))
        .attr('text-anchor', 'middle')
        .attr('fill', l.color).attr('opacity', 0.3)
        .attr('class', 'text-xs font-semibold')
        .text(l.text);
    });

    // Axes
    g.append('g').attr('transform', `translate(0,${innerH})`).call(
      d3.axisBottom(x).ticks(6).tickFormat((d) => `$${(Number(d) / 1000).toFixed(0)}k`)
    ).selectAll('text').attr('class', 'text-[10px]').attr('fill', colors.textMuted);

    g.append('g').call(d3.axisLeft(y).ticks(5)).selectAll('text').attr('class', 'text-[10px]').attr('fill', colors.textMuted);

    // Axis labels
    svg.append('text').attr('x', width / 2).attr('y', height - 6).attr('text-anchor', 'middle').attr('class', 'text-xs').attr('fill', colors.textMuted).text('Estimated Cost');
    svg.append('text').attr('transform', 'rotate(-90)').attr('x', -height / 2).attr('y', 14).attr('text-anchor', 'middle').attr('class', 'text-xs').attr('fill', colors.textMuted).text('Impact Score');

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'fixed pointer-events-none bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl opacity-0 transition-opacity z-50');

    // Points with animated entry
    g.selectAll('.point')
      .data(data)
      .enter()
      .append('circle')
      .attr('cx', (d) => x(d.x))
      .attr('cy', (d) => y(d.y))
      .attr('fill', (d) => PRIORITY_COLORS[d.priority] || '#94a3b8')
      .attr('stroke', 'white')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .attr('r', 0)
      .transition()
      .duration(600)
      .delay((_, i) => i * 60)
      .ease(d3.easeBackOut)
      .attr('r', 8);

    // Hover
    g.selectAll('circle')
      .on('mouseover', function (event, d: any) {
        d3.select(this).transition().duration(150).attr('r', 12);
        tooltip.style('opacity', '1')
          .html(`<strong>${d.name}</strong><br/>Cost: $${d.x.toLocaleString()}<br/>Impact: ${d.y.toFixed(1)}<br/>Priority: ${d.priority}`)
          .style('left', `${event.pageX + 12}px`)
          .style('top', `${event.pageY - 40}px`);
      })
      .on('mousemove', function (event) {
        tooltip.style('left', `${event.pageX + 12}px`).style('top', `${event.pageY - 40}px`);
      })
      .on('mouseout', function () {
        d3.select(this).transition().duration(150).attr('r', 8);
        tooltip.style('opacity', '0');
      });

    return () => { tooltip.remove(); };
  }, [data, height]);

  if (!data.length) {
    return <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height }}>No data to display</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
}
