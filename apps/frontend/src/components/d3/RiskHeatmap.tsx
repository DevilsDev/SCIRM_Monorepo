import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface HeatmapCell {
  category: string;
  severity: string;
  value: number;
}

interface RiskHeatmapProps {
  data: HeatmapCell[];
  height?: number;
}

const SEVERITY_ORDER = ['low', 'medium', 'high', 'critical'];

export default function RiskHeatmap({ data, height = 220 }: RiskHeatmapProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !data.length) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const margin = { top: 30, right: 20, bottom: 50, left: 100 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    d3.select(container).selectAll('*').remove();

    const svg = d3.select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height);

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const categories = [...new Set(data.map((d) => d.category))];
    const severities = SEVERITY_ORDER.filter((s) => data.some((d) => d.severity === s));

    const x = d3.scaleBand().domain(severities).range([0, innerW]).padding(0.08);
    const y = d3.scaleBand().domain(categories).range([0, innerH]).padding(0.08);
    const maxVal = d3.max(data, (d) => d.value) || 1;
    const colorScale = d3.scaleSequential(d3.interpolateYlOrRd).domain([0, maxVal]);

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'fixed pointer-events-none bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl opacity-0 transition-opacity z-50');

    // Cells with animated entry
    g.selectAll('.cell')
      .data(data)
      .enter()
      .append('rect')
      .attr('x', (d) => x(d.severity) || 0)
      .attr('y', (d) => y(d.category) || 0)
      .attr('width', x.bandwidth())
      .attr('height', y.bandwidth())
      .attr('rx', 4)
      .attr('fill', '#f3f4f6')
      .style('cursor', 'pointer')
      .transition()
      .duration(600)
      .delay((_, i) => i * 40)
      .attr('fill', (d) => (d.value > 0 ? colorScale(d.value) : '#f9fafb'));

    // Cell value labels
    g.selectAll('.cell-label')
      .data(data)
      .enter()
      .append('text')
      .attr('x', (d) => (x(d.severity) || 0) + x.bandwidth() / 2)
      .attr('y', (d) => (y(d.category) || 0) + y.bandwidth() / 2 + 4)
      .attr('text-anchor', 'middle')
      .attr('class', 'text-xs font-semibold')
      .attr('fill', (d) => (d.value > maxVal * 0.6 ? 'white' : '#374151'))
      .attr('opacity', 0)
      .transition()
      .delay((_, i) => i * 40 + 400)
      .duration(300)
      .attr('opacity', 1)
      .text((d) => d.value || '');

    // Hover
    g.selectAll('rect')
      .on('mouseover', function (event, d: any) {
        d3.select(this).attr('stroke', '#111827').attr('stroke-width', 2);
        tooltip.style('opacity', '1')
          .html(`<strong class="capitalize">${d.category}</strong> × <strong class="capitalize">${d.severity}</strong><br/>${d.value} risk${d.value !== 1 ? 's' : ''}`)
          .style('left', `${event.pageX + 12}px`)
          .style('top', `${event.pageY - 28}px`);
      })
      .on('mousemove', function (event) {
        tooltip.style('left', `${event.pageX + 12}px`).style('top', `${event.pageY - 28}px`);
      })
      .on('mouseout', function () {
        d3.select(this).attr('stroke', 'none');
        tooltip.style('opacity', '0');
      });

    // Axes
    g.append('g').attr('transform', `translate(0,${innerH})`).call(d3.axisBottom(x).tickSize(0))
      .select('.domain').remove();
    g.selectAll('.tick text').attr('class', 'fill-gray-600 text-xs capitalize');

    g.append('g').call(d3.axisLeft(y).tickSize(0)).select('.domain').remove();
    g.selectAll('.tick text').attr('class', 'fill-gray-600 text-xs capitalize');

    // Title
    svg.append('text').attr('x', width / 2).attr('y', 16).attr('text-anchor', 'middle')
      .attr('class', 'fill-gray-400 text-[10px]').text('Category × Severity');

    return () => { tooltip.remove(); };
  }, [data, height]);

  if (!data.length) {
    return <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height }}>No heatmap data</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
}
