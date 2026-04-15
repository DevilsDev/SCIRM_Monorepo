import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { useTranslation } from 'react-i18next';
import { getThemeColors } from './theme';

interface DonutData {
  name: string;
  value: number;
}

const COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
};

interface DonutChartProps {
  data: DonutData[];
  width?: number;
  height?: number;
}

export default function DonutChart({ data, width = 320, height = 280 }: DonutChartProps) {
  const { t } = useTranslation();
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;

    // Filter out zero-value items so they don't render as invisible slivers
    const filteredData = data.filter((d) => d.value > 0);

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    if (!filteredData.length) return;

    const colors = getThemeColors();

    const radius = Math.min(width, height) / 2 - 20;
    const innerRadius = radius * 0.55;
    const g = svg.append('g').attr('transform', `translate(${width / 2},${height / 2})`);

    const pie = d3.pie<DonutData>().value((d) => d.value).sort(null).padAngle(0.03);
    const arc = d3.arc<d3.PieArcDatum<DonutData>>().innerRadius(innerRadius).outerRadius(radius).cornerRadius(4);
    const arcHover = d3.arc<d3.PieArcDatum<DonutData>>().innerRadius(innerRadius).outerRadius(radius + 10).cornerRadius(4);

    const total = filteredData.reduce((s, d) => s + d.value, 0);

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'fixed pointer-events-none bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl opacity-0 transition-opacity z-50');

    // Arcs with animated entry
    const arcs = g.selectAll('.arc').data(pie(filteredData)).enter().append('g').attr('class', 'arc');

    arcs.append('path')
      .attr('fill', (d) => COLORS[d.data.name] || '#94a3b8')
      .attr('stroke', colors.stroke)
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .transition()
      .duration(800)
      .ease(d3.easeCubicOut)
      .attrTween('d', function (d) {
        const interpolate = d3.interpolate({ startAngle: 0, endAngle: 0 }, d);
        return (t) => arc(interpolate(t)) || '';
      });

    // Hover effects
    arcs.selectAll('path')
      .on('mouseover', function (event, d) {
        d3.select(this).transition().duration(200).attr('d', (d: any) => arcHover(d) || '');
        tooltip.style('opacity', '1')
          .html(`<strong class="capitalize">${d.data.name}</strong><br/>${d.data.value} risks (${Math.round((d.data.value / total) * 100)}%)`)
          .style('left', `${event.pageX + 12}px`)
          .style('top', `${event.pageY - 28}px`);
      })
      .on('mousemove', function (event) {
        tooltip.style('left', `${event.pageX + 12}px`).style('top', `${event.pageY - 28}px`);
      })
      .on('mouseout', function () {
        d3.select(this).transition().duration(200).attr('d', (d: any) => arc(d) || '');
        tooltip.style('opacity', '0');
      });

    // Center text — uses theme-aware colors
    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '-0.2em')
      .attr('fill', colors.text)
      .attr('font-size', '28px')
      .attr('font-weight', 'bold')
      .text(total);

    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '1.4em')
      .attr('fill', colors.textMuted)
      .attr('font-size', '12px')
      .text('Total Risks');

    // Legend — only show items with value > 0
    const legendItems = filteredData;
    const legendWidth = legendItems.length * 80;
    const legend = svg.append('g').attr('transform', `translate(${width / 2 - legendWidth / 2},${height - 20})`);
    legendItems.forEach((d, i) => {
      const lg = legend.append('g').attr('transform', `translate(${i * 80}, 0)`);
      lg.append('rect').attr('width', 10).attr('height', 10).attr('rx', 2).attr('fill', COLORS[d.name] || '#94a3b8');
      lg.append('text').attr('x', 14).attr('y', 9).attr('fill', colors.textLight).attr('font-size', '10px').style('text-transform', 'capitalize').text(d.name);
    });

    return () => { tooltip.remove(); };
  }, [data, width, height]);

  if (!data.length || data.every((d) => d.value === 0)) {
    return <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height }}>{t('common.noRiskData', 'No risk data available')}</div>;
  }

  return <svg ref={svgRef} width={width} height={height} />;
}
