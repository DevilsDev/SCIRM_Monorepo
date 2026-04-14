import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface RadarData {
  dimension: string;
  label: string;
  score: number;
}

interface RadarChartProps {
  data: RadarData[];
  size?: number;
}

const DIMENSION_COLORS: Record<string, string> = {
  esg: '#22c55e',
  cyber: '#8b5cf6',
  financial: '#3b82f6',
  geopolitical: '#f97316',
  catastrophic: '#ef4444',
  operational: '#eab308',
  regulatory: '#06b6d4',
};

export default function RadarChart({ data, size = 300 }: RadarChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data.length) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = 50;
    const radius = size / 2 - margin;
    const center = size / 2;
    const levels = 5;
    const angleSlice = (Math.PI * 2) / data.length;

    const g = svg.append('g').attr('transform', `translate(${center},${center})`);

    const rScale = d3.scaleLinear().domain([0, 100]).range([0, radius]);

    // Grid circles
    for (let lvl = 1; lvl <= levels; lvl++) {
      const r = (radius / levels) * lvl;
      g.append('circle')
        .attr('r', r)
        .attr('fill', 'none')
        .attr('stroke', '#e5e7eb')
        .attr('stroke-width', 0.5);

      g.append('text')
        .attr('x', 4)
        .attr('y', -r + 4)
        .attr('class', 'text-[8px] fill-gray-400')
        .text(`${(lvl / levels) * 100}`);
    }

    // Axis lines + labels
    data.forEach((d, i) => {
      const angle = angleSlice * i - Math.PI / 2;
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius;

      g.append('line')
        .attr('x1', 0).attr('y1', 0)
        .attr('x2', x).attr('y2', y)
        .attr('stroke', '#d1d5db')
        .attr('stroke-width', 0.5);

      const labelX = Math.cos(angle) * (radius + 20);
      const labelY = Math.sin(angle) * (radius + 20);
      g.append('text')
        .attr('x', labelX)
        .attr('y', labelY)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('class', 'text-[9px] font-medium fill-gray-600')
        .text(d.label.length > 12 ? d.label.slice(0, 10) + '..' : d.label);
    });

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'fixed pointer-events-none bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl opacity-0 transition-opacity z-50');

    // Data polygon with animation
    const lineGenerator = d3.lineRadial<RadarData>()
      .radius((d) => rScale(d.score))
      .angle((_, i) => i * angleSlice)
      .curve(d3.curveLinearClosed);

    // Filled area
    g.append('path')
      .datum(data)
      .attr('fill', '#3b82f6')
      .attr('fill-opacity', 0)
      .attr('stroke', '#3b82f6')
      .attr('stroke-width', 2)
      .attr('d', lineGenerator)
      .transition()
      .duration(800)
      .ease(d3.easeCubicOut)
      .attr('fill-opacity', 0.15);

    // Animated line
    const path = g.append('path')
      .datum(data)
      .attr('fill', 'none')
      .attr('stroke', '#3b82f6')
      .attr('stroke-width', 2.5)
      .attr('d', lineGenerator);

    const totalLength = (path.node() as SVGPathElement)?.getTotalLength() || 0;
    path.attr('stroke-dasharray', `${totalLength} ${totalLength}`)
      .attr('stroke-dashoffset', totalLength)
      .transition().duration(1000).ease(d3.easeCubicOut)
      .attr('stroke-dashoffset', 0);

    // Data points
    data.forEach((d, i) => {
      const angle = angleSlice * i - Math.PI / 2;
      const x = Math.cos(angle) * rScale(d.score);
      const y = Math.sin(angle) * rScale(d.score);
      const color = DIMENSION_COLORS[d.dimension] || '#3b82f6';

      g.append('circle')
        .attr('cx', x).attr('cy', y)
        .attr('r', 0)
        .attr('fill', color)
        .attr('stroke', 'white')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .transition()
        .delay(800 + i * 60)
        .duration(300)
        .ease(d3.easeBackOut)
        .attr('r', 5);

      // Invisible larger hit area for hover
      g.append('circle')
        .attr('cx', x).attr('cy', y)
        .attr('r', 15)
        .attr('fill', 'transparent')
        .style('cursor', 'pointer')
        .on('mouseover', (event) => {
          tooltip.style('opacity', '1')
            .html(`<strong>${d.label}</strong><br/>Score: ${d.score.toFixed(0)}/100`)
            .style('left', `${event.pageX + 12}px`)
            .style('top', `${event.pageY - 28}px`);
        })
        .on('mousemove', (event) => {
          tooltip.style('left', `${event.pageX + 12}px`).style('top', `${event.pageY - 28}px`);
        })
        .on('mouseout', () => { tooltip.style('opacity', '0'); });
    });

    return () => { tooltip.remove(); };
  }, [data, size]);

  if (!data.length) {
    return <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height: size }}>No dimension data</div>;
  }

  return <svg ref={svgRef} width={size} height={size} />;
}
