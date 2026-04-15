import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface GaugeChartProps {
  value: number; // 0-100
  label?: string;
  size?: number;
}

export default function GaugeChart({ value, label = 'Score', size = 140 }: GaugeChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const radius = size / 2 - 10;
    const thickness = 12;
    const g = svg.append('g').attr('transform', `translate(${size / 2},${size / 2})`);

    const startAngle = -Math.PI * 0.75;
    const endAngle = Math.PI * 0.75;
    const scale = d3.scaleLinear().domain([0, 100]).range([startAngle, endAngle]).clamp(true);

    // Background arc
    const bgArc = d3.arc().innerRadius(radius - thickness).outerRadius(radius).startAngle(startAngle).endAngle(endAngle).cornerRadius(6);
    g.append('path').attr('d', bgArc as any).attr('fill', '#e5e7eb');

    // Value arc with animation
    const color = value >= 80 ? '#22c55e' : value >= 60 ? '#eab308' : value >= 40 ? '#f97316' : '#ef4444';
    const valueArc = d3.arc().innerRadius(radius - thickness).outerRadius(radius).startAngle(startAngle).cornerRadius(6);

    g.append('path')
      .attr('fill', color)
      .transition()
      .duration(1000)
      .ease(d3.easeCubicOut)
      .attrTween('d', function () {
        const interpolate = d3.interpolate(startAngle, scale(value));
        return (t) => valueArc.endAngle(interpolate(t))({} as any) || '';
      });

    // Center value
    const text = g.append('text').attr('text-anchor', 'middle').attr('dy', '0.1em').attr('class', 'text-2xl font-bold').attr('fill', '#111827');
    text.transition().duration(1000).tween('text', function () {
      const i = d3.interpolateNumber(0, value);
      return function (t) { (this as any).textContent = `${Math.round(i(t))}%`; };
    });

    // Label
    g.append('text').attr('text-anchor', 'middle').attr('dy', '1.8em').attr('class', 'text-[10px]').attr('fill', '#6b7280').text(label);

  }, [value, label, size]);

  return <svg ref={svgRef} width={size} height={size} />;
}
