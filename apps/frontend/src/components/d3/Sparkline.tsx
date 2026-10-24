import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}

export default function Sparkline({ data, width = 80, height = 30, color = '#3b82f6' }: SparklineProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data.length) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const x = d3.scaleLinear().domain([0, data.length - 1]).range([2, width - 2]);
    const y = d3.scaleLinear().domain([d3.min(data) || 0, d3.max(data) || 1]).range([height - 2, 2]);

    // Area gradient
    const gradientId = `spark-grad-${Math.random().toString(36).slice(2)}`;
    const defs = svg.append('defs');
    const gradient = defs.append('linearGradient').attr('id', gradientId).attr('x1', '0').attr('y1', '0').attr('x2', '0').attr('y2', '1');
    gradient.append('stop').attr('offset', '0%').attr('stop-color', color).attr('stop-opacity', 0.3);
    gradient.append('stop').attr('offset', '100%').attr('stop-color', color).attr('stop-opacity', 0);

    const area = d3.area<number>().x((_, i) => x(i)).y0(height).y1((d) => y(d)).curve(d3.curveMonotoneX);
    const line = d3.line<number>().x((_, i) => x(i)).y((d) => y(d)).curve(d3.curveMonotoneX);

    // Animated area
    svg.append('path').datum(data).attr('fill', `url(#${gradientId})`).attr('d', area);

    // Animated line
    const path = svg.append('path').datum(data).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 1.5).attr('d', line);
    const totalLength = (path.node() as SVGPathElement)?.getTotalLength() || 0;
    path.attr('stroke-dasharray', `${totalLength} ${totalLength}`).attr('stroke-dashoffset', totalLength)
      .transition().duration(800).ease(d3.easeCubicOut).attr('stroke-dashoffset', 0);

    // End dot
    svg.append('circle')
      .attr('cx', x(data.length - 1))
      .attr('cy', y(data[data.length - 1]))
      .attr('r', 2.5)
      .attr('fill', color)
      .attr('opacity', 0)
      .transition().delay(800).duration(200).attr('opacity', 1);

  }, [data, width, height, color]);

  if (!data.length) return null;

  return <svg ref={svgRef} width={width} height={height} />;
}
