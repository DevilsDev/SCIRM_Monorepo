import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface BarData {
  name: string;
  value: number;
  color?: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
};

interface AnimatedBarsProps {
  data: BarData[];
  height?: number;
  colorField?: string;
  valueLabel?: string;
  maxValue?: number;
}

export default function AnimatedBars({ data, height = 300, colorField, valueLabel = '%', maxValue }: AnimatedBarsProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !data.length) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const margin = { top: 20, right: 60, bottom: 40, left: 120 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    d3.select(container).selectAll('*').remove();

    const svg = d3.select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height);

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const y = d3.scaleBand().domain(data.map((d) => d.name)).range([0, innerH]).padding(0.35);
    const x = d3.scaleLinear().domain([0, maxValue || d3.max(data, (d) => d.value) || 100]).range([0, innerW]);

    // Grid lines
    g.append('g')
      .attr('class', 'grid')
      .call(d3.axisBottom(x).tickSize(innerH).tickFormat(() => '').ticks(5))
      .attr('stroke-opacity', 0.1)
      .select('.domain').remove();

    // Y axis
    g.append('g')
      .call(d3.axisLeft(y).tickSize(0))
      .select('.domain').remove();
    g.selectAll('.tick text')
      .attr('class', 'fill-gray-700 text-xs capitalize');

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'fixed pointer-events-none bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl opacity-0 transition-opacity z-50');

    // Bars with animation
    g.selectAll('.bar')
      .data(data)
      .enter()
      .append('rect')
      .attr('class', 'bar')
      .attr('y', (d) => y(d.name) || 0)
      .attr('height', y.bandwidth())
      .attr('x', 0)
      .attr('rx', 4)
      .attr('fill', (d) => {
        if (d.color) return d.color;
        if (colorField) return SEVERITY_COLORS[(d as any)[colorField]] || '#3b82f6';
        return '#3b82f6';
      })
      .style('cursor', 'pointer')
      .attr('width', 0)
      .transition()
      .duration(800)
      .delay((_, i) => i * 100)
      .ease(d3.easeCubicOut)
      .attr('width', (d) => x(d.value));

    // Hover
    g.selectAll('.bar')
      .on('mouseover', function (event, d: any) {
        d3.select(this).attr('opacity', 0.8);
        tooltip.style('opacity', '1')
          .html(`<strong class="capitalize">${d.name}</strong><br/>${d.value}${valueLabel}`)
          .style('left', `${event.pageX + 12}px`)
          .style('top', `${event.pageY - 28}px`);
      })
      .on('mousemove', function (event) {
        tooltip.style('left', `${event.pageX + 12}px`).style('top', `${event.pageY - 28}px`);
      })
      .on('mouseout', function () {
        d3.select(this).attr('opacity', 1);
        tooltip.style('opacity', '0');
      });

    // Value labels
    g.selectAll('.label')
      .data(data)
      .enter()
      .append('text')
      .attr('class', 'fill-gray-700 text-xs font-semibold')
      .attr('y', (d) => (y(d.name) || 0) + y.bandwidth() / 2 + 4)
      .attr('x', 0)
      .transition()
      .duration(800)
      .delay((_, i) => i * 100)
      .attr('x', (d) => x(d.value) + 8)
      .text((d) => `${d.value}${valueLabel}`);

    return () => { tooltip.remove(); };
  }, [data, height, colorField, valueLabel, maxValue]);

  if (!data.length) {
    return <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height }}>No data available</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
}
