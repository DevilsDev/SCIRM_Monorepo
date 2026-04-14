import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { getThemeColors, isDarkMode } from './theme';

interface FlowNode {
  id: string;
  type: string;
  label: string;
  risk_score?: number;
  risk_tier?: string;
  severity?: string;
  supplier_type?: string;
  region?: string;
  country_code?: string;
  risk_category?: string;
}

interface FlowEdge {
  source: string;
  target: string;
  relationship: string;
}

const TIER_COLORS: Record<string, string> = {
  low: '#22c55e',
  medium: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
};

const SEVERITY_COLORS: Record<string, string> = {
  low: '#22c55e',
  medium: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
};

interface SupplyChainFlowProps {
  nodes: FlowNode[];
  edges: FlowEdge[];
  height?: number;
}

export default function SupplyChainFlow({ nodes, edges, height = 520 }: SupplyChainFlowProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !nodes.length) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const margin = { top: 50, right: 40, bottom: 40, left: 40 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    d3.select(container).selectAll('*').remove();
    const colors = getThemeColors();
    const isDark = isDarkMode();

    const svg = d3.select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height)
      .style('overflow', 'visible');

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    // Layer groups — links behind, nodes on top
    const linkLayer = g.append('g').attr('class', 'links');
    const nodeLayer = g.append('g').attr('class', 'nodes');
    const labelLayer = g.append('g').attr('class', 'labels');

    // Separate and deduplicate nodes
    const suppliers = nodes.filter((n) => n.type === 'supplier');
    const orgs = [...new Map(nodes.filter((n) => n.type === 'organization').map((n) => [n.id, n])).values()];
    const riskNodes = nodes.filter((n) => n.type === 'risk');

    // Aggregate risks by category instead of showing each one
    const riskCategories: Record<string, { count: number; severities: string[] }> = {};
    riskNodes.forEach((r) => {
      const cat = r.risk_category || r.label.replace(' Risk', '').toLowerCase() || 'general';
      if (!riskCategories[cat]) riskCategories[cat] = { count: 0, severities: [] };
      riskCategories[cat].count++;
      if (r.severity) riskCategories[cat].severities.push(r.severity);
    });

    const aggregatedRisks = Object.entries(riskCategories).map(([cat, data]) => {
      const worstSeverity = data.severities.includes('critical') ? 'critical'
        : data.severities.includes('high') ? 'high'
        : data.severities.includes('medium') ? 'medium' : 'low';
      return { id: `risk-${cat}`, label: cat, count: data.count, severity: worstSeverity };
    });

    // Tier X positions (3 columns)
    const tierX = [innerW * 0.10, innerW * 0.45, innerW * 0.80];

    // Minimum spacing per node (largest radius + labels + padding)
    const minNodeSpacing = 130;
    const maxItems = Math.max(suppliers.length, orgs.length, aggregatedRisks.length);
    const requiredH = maxItems * minNodeSpacing;
    const effectiveH = Math.max(innerH, requiredH);

    // Resize SVG if content overflows
    if (effectiveH > innerH) {
      svg.attr('height', effectiveH + margin.top + margin.bottom);
    }

    // Position suppliers
    const supplierSpacing = effectiveH / (suppliers.length + 1);
    const posSuppliers = suppliers.map((s, i) => ({ ...s, x: tierX[0], y: supplierSpacing * (i + 1) }));

    // Position orgs (center, vertically centered)
    const orgSpacing = effectiveH / (orgs.length + 1);
    const posOrgs = orgs.map((o, i) => ({ ...o, x: tierX[1], y: orgSpacing * (i + 1) }));

    // Position aggregated risks
    const riskSpacing = effectiveH / (aggregatedRisks.length + 1);
    const posRisks = aggregatedRisks.map((r, i) => ({ ...r, x: tierX[2], y: riskSpacing * (i + 1) }));

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'fixed pointer-events-none bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl opacity-0 transition-opacity z-50 max-w-xs');

    // Tier labels
    [
      { label: 'SUPPLIERS', x: tierX[0], color: '#3b82f6' },
      { label: 'ORGANIZATION', x: tierX[1], color: '#8b5cf6' },
      { label: 'RISK CATEGORIES', x: tierX[2], color: '#ef4444' },
    ].forEach(({ label, x, color }) => {
      labelLayer.append('text').attr('x', x).attr('y', -20).attr('text-anchor', 'middle')
        .attr('fill', color).attr('font-size', '11px').attr('font-weight', 'bold')
        .attr('letter-spacing', '1px').text(label);
    });

    // Draw links: suppliers → org
    const defs = svg.append('defs');
    posSuppliers.forEach((supplier, i) => {
      const target = posOrgs[0] || posOrgs[posOrgs.length - 1];
      if (!target) return;

      const gradId = `flow-s-${i}`;
      const sColor = supplier.risk_tier ? TIER_COLORS[supplier.risk_tier] : '#3b82f6';
      const gradient = defs.append('linearGradient').attr('id', gradId).attr('x1', '0%').attr('y1', '0%').attr('x2', '100%').attr('y2', '0%');
      gradient.append('stop').attr('offset', '0%').attr('stop-color', sColor).attr('stop-opacity', 0.6);
      gradient.append('stop').attr('offset', '100%').attr('stop-color', '#8b5cf6').attr('stop-opacity', 0.4);

      const strokeW = Math.max(2, Math.min((supplier.risk_score || 50) / 8, 10));
      const midX = (supplier.x + target.x) / 2;

      linkLayer.append('path')
        .attr('d', `M${supplier.x},${supplier.y} C${midX},${supplier.y} ${midX},${target.y} ${target.x},${target.y}`)
        .attr('fill', 'none').attr('stroke', `url(#${gradId})`).attr('stroke-width', strokeW)
        .attr('opacity', 0)
        .on('mouseover', function (event) {
          d3.select(this).attr('opacity', 0.9).attr('stroke-width', strokeW + 2);
          tooltip.style('opacity', '1').html(`<strong>${supplier.label}</strong> → <strong>${target.label}</strong><br/>Risk: ${supplier.risk_score || '?'}/100`)
            .style('left', `${event.pageX + 12}px`).style('top', `${event.pageY - 30}px`);
        })
        .on('mousemove', (event) => tooltip.style('left', `${event.pageX + 12}px`).style('top', `${event.pageY - 30}px`))
        .on('mouseout', function () { d3.select(this).attr('opacity', 1).attr('stroke-width', strokeW); tooltip.style('opacity', '0'); })
        .transition().duration(600).delay(i * 80).attr('opacity', 1);
    });

    // Draw links: org → risk categories
    posRisks.forEach((risk, i) => {
      const source = posOrgs[0];
      if (!source) return;

      const gradId = `flow-r-${i}`;
      const rColor = SEVERITY_COLORS[risk.severity] || '#ef4444';
      const gradient = defs.append('linearGradient').attr('id', gradId).attr('x1', '0%').attr('y1', '0%').attr('x2', '100%').attr('y2', '0%');
      gradient.append('stop').attr('offset', '0%').attr('stop-color', '#8b5cf6').attr('stop-opacity', 0.4);
      gradient.append('stop').attr('offset', '100%').attr('stop-color', rColor).attr('stop-opacity', 0.6);

      const strokeW = Math.max(2, Math.min(risk.count * 2, 10));
      const midX = (source.x + risk.x) / 2;

      linkLayer.append('path')
        .attr('d', `M${source.x},${source.y} C${midX},${source.y} ${midX},${risk.y} ${risk.x},${risk.y}`)
        .attr('fill', 'none').attr('stroke', `url(#${gradId})`).attr('stroke-width', strokeW)
        .attr('opacity', 0)
        .transition().duration(600).delay(posSuppliers.length * 80 + i * 80).attr('opacity', 1);
    });

    // Draw supplier nodes
    posSuppliers.forEach((node, i) => {
      const nodeColor = node.risk_tier ? TIER_COLORS[node.risk_tier] : '#3b82f6';
      const nodeG = nodeLayer.append('g').attr('transform', `translate(${node.x},${node.y})`).style('cursor', 'pointer');

      if ((node.risk_score || 0) > 60) {
        nodeG.append('circle').attr('r', 32).attr('fill', nodeColor).attr('opacity', 0)
          .transition().duration(800).delay(i * 60).attr('opacity', 0.15);
      }

      nodeG.append('circle').attr('r', 0).attr('fill', nodeColor).attr('stroke', colors.stroke).attr('stroke-width', 3)
        .transition().duration(500).delay(i * 60).ease(d3.easeBackOut).attr('r', 24);

      nodeG.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em').attr('fill', 'white')
        .attr('font-size', '14px').attr('font-weight', 'bold').attr('opacity', 0).text('S')
        .transition().delay(i * 60 + 300).duration(200).attr('opacity', 1);

      labelLayer.append('text').attr('x', node.x).attr('y', node.y + 38).attr('text-anchor', 'middle')
        .attr('font-size', '11px').attr('font-weight', '500').attr('fill', colors.text).text(node.label);

      labelLayer.append('text').attr('x', node.x).attr('y', node.y + 52).attr('text-anchor', 'middle')
        .attr('font-size', '9px').attr('fill', colors.textMuted).text(`Risk: ${(node.risk_score || 0).toFixed(0)}/100`);

      nodeG.on('mouseover', function (event) {
        d3.select(this).select('circle:nth-child(2)').transition().duration(150).attr('r', 28);
        tooltip.style('opacity', '1')
          .html(`<strong>${node.label}</strong><br/>Type: ${node.supplier_type || 'supplier'}<br/>Region: ${node.country_code || ''} ${node.region || ''}<br/>Risk: ${node.risk_score || '?'}/100 (${node.risk_tier || '?'})`)
          .style('left', `${event.pageX + 14}px`).style('top', `${event.pageY - 30}px`);
      })
      .on('mouseout', function () {
        d3.select(this).select('circle:nth-child(2)').transition().duration(150).attr('r', 24);
        tooltip.style('opacity', '0');
      });
    });

    // Draw org nodes
    posOrgs.forEach((node, i) => {
      const nodeG = nodeLayer.append('g').attr('transform', `translate(${node.x},${node.y})`);

      nodeG.append('circle').attr('r', 0).attr('fill', '#8b5cf6').attr('stroke', colors.stroke).attr('stroke-width', 3)
        .transition().duration(500).delay(posSuppliers.length * 60 + 100).ease(d3.easeBackOut).attr('r', 36);

      nodeG.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em').attr('fill', 'white')
        .attr('font-size', '18px').attr('font-weight', 'bold').attr('opacity', 0).text('O')
        .transition().delay(posSuppliers.length * 60 + 400).duration(200).attr('opacity', 1);

      const shortLabel = node.label.length > 15 ? node.label.slice(0, 13) + '..' : node.label;
      labelLayer.append('text').attr('x', node.x).attr('y', node.y + 50).attr('text-anchor', 'middle')
        .attr('font-size', '11px').attr('font-weight', '500').attr('fill', colors.text).text(shortLabel);
    });

    // Draw aggregated risk nodes (category bubbles with count)
    posRisks.forEach((risk, i) => {
      const rColor = SEVERITY_COLORS[risk.severity] || '#ef4444';
      const radius = Math.max(18, Math.min(risk.count * 2 + 14, 30));
      const delay = posSuppliers.length * 60 + 200 + i * 80;
      const nodeG = nodeLayer.append('g').attr('transform', `translate(${risk.x},${risk.y})`).style('cursor', 'pointer');

      nodeG.append('circle').attr('r', 0).attr('fill', rColor).attr('stroke', colors.stroke).attr('stroke-width', 2)
        .transition().duration(500).delay(delay).ease(d3.easeBackOut).attr('r', radius);

      // Count inside circle
      nodeG.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em').attr('fill', 'white')
        .attr('font-size', `${Math.max(12, radius * 0.5)}px`).attr('font-weight', 'bold')
        .attr('opacity', 0).text(risk.count)
        .transition().delay(delay + 300).duration(200).attr('opacity', 1);

      // Category label below bubble — in labelLayer so it renders on top of all circles
      labelLayer.append('text').attr('x', risk.x).attr('y', risk.y + radius + 18).attr('text-anchor', 'middle')
        .attr('font-size', '12px').attr('font-weight', '600').attr('fill', colors.text)
        .style('text-transform', 'capitalize').text(risk.label);

      // Severity label
      labelLayer.append('text').attr('x', risk.x).attr('y', risk.y + radius + 33).attr('text-anchor', 'middle')
        .attr('font-size', '10px').attr('fill', rColor)
        .style('text-transform', 'capitalize').text(`${risk.severity} (${risk.count})`);

      nodeG.on('mouseover', function (event) {
        d3.select(this).select('circle').transition().duration(150).attr('r', radius + 4);
        tooltip.style('opacity', '1')
          .html(`<strong class="capitalize">${risk.label}</strong><br/>${risk.count} risks<br/>Worst severity: <span style="color:${rColor}">${risk.severity}</span>`)
          .style('left', `${event.pageX + 14}px`).style('top', `${event.pageY - 30}px`);
      })
      .on('mouseout', function () {
        d3.select(this).select('circle').transition().duration(150).attr('r', radius);
        tooltip.style('opacity', '0');
      });
    });

    return () => { tooltip.remove(); };
  }, [nodes, edges, height]);

  if (!nodes.length) {
    return <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height }}>No supply chain data</div>;
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
}
