import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

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

const TYPE_CONFIG: Record<string, { color: string; icon: string; tier: number }> = {
  supplier: { color: '#3b82f6', icon: 'S', tier: 0 },
  organization: { color: '#8b5cf6', icon: 'O', tier: 1 },
  risk: { color: '#ef4444', icon: '!', tier: 2 },
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
    const margin = { top: 40, right: 40, bottom: 40, left: 40 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    d3.select(container).selectAll('*').remove();

    const svg = d3.select(container)
      .append('svg')
      .attr('width', width)
      .attr('height', height);

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    // Separate nodes by tier
    const suppliers = nodes.filter((n) => n.type === 'supplier');
    const orgs = nodes.filter((n) => n.type === 'organization');
    const risks = nodes.filter((n) => n.type === 'risk');

    // Tier X positions
    const tierX = [innerW * 0.08, innerW * 0.48, innerW * 0.88];

    // Position nodes within each tier
    const positionTier = (tierNodes: FlowNode[], tierIdx: number) => {
      const spacing = innerH / (tierNodes.length + 1);
      return tierNodes.map((node, i) => ({
        ...node,
        x: tierX[tierIdx],
        y: spacing * (i + 1),
      }));
    };

    const posSuppliers = positionTier(suppliers, 0);
    const posOrgs = positionTier(orgs, 1);
    const posRisks = positionTier(risks, 2);
    const allPositioned = [...posSuppliers, ...posOrgs, ...posRisks];
    const posMap = new Map(allPositioned.map((n) => [n.id, n]));

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'fixed pointer-events-none bg-gray-900 text-white text-xs px-3 py-2 rounded-lg shadow-xl opacity-0 transition-opacity z-50 max-w-xs');

    // Tier labels
    const tierLabels = [
      { label: 'SUPPLIERS', x: tierX[0], color: '#3b82f6' },
      { label: 'ORGANIZATION', x: tierX[1], color: '#8b5cf6' },
      { label: 'RISKS', x: tierX[2], color: '#ef4444' },
    ];
    tierLabels.forEach(({ label, x, color }) => {
      g.append('text')
        .attr('x', x)
        .attr('y', -14)
        .attr('text-anchor', 'middle')
        .attr('class', 'text-[11px] font-bold tracking-wider')
        .attr('fill', color)
        .attr('opacity', 0.6)
        .text(label);
    });

    // Draw links as curved paths with gradient
    const defs = svg.append('defs');

    edges.forEach((edge, i) => {
      const source = posMap.get(edge.source);
      const target = posMap.get(edge.target);
      if (!source || !target) return;

      // Gradient for each link
      const gradId = `flow-grad-${i}`;
      const sourceColor = source.risk_tier ? TIER_COLORS[source.risk_tier] || '#94a3b8' : TYPE_CONFIG[source.type]?.color || '#94a3b8';
      const targetColor = target.severity ? TIER_COLORS[target.severity] || '#94a3b8' : TYPE_CONFIG[target.type]?.color || '#94a3b8';

      const gradient = defs.append('linearGradient')
        .attr('id', gradId)
        .attr('x1', '0%').attr('y1', '0%')
        .attr('x2', '100%').attr('y2', '0%');
      gradient.append('stop').attr('offset', '0%').attr('stop-color', sourceColor).attr('stop-opacity', 0.5);
      gradient.append('stop').attr('offset', '100%').attr('stop-color', targetColor).attr('stop-opacity', 0.5);

      // Link thickness based on risk score
      const riskScore = source.risk_score || 50;
      const strokeWidth = Math.max(2, Math.min(riskScore / 10, 12));

      // Curved path
      const sx = (source as any).x;
      const sy = (source as any).y;
      const tx = (target as any).x;
      const ty = (target as any).y;
      const midX = (sx + tx) / 2;

      const path = g.append('path')
        .attr('d', `M${sx},${sy} C${midX},${sy} ${midX},${ty} ${tx},${ty}`)
        .attr('fill', 'none')
        .attr('stroke', `url(#${gradId})`)
        .attr('stroke-width', strokeWidth)
        .attr('opacity', 0)
        .style('cursor', 'pointer');

      // Animated entry
      path.transition()
        .duration(800)
        .delay(i * 50)
        .attr('opacity', 1);

      // Hover
      path.on('mouseover', function (event) {
        d3.select(this).attr('opacity', 0.9).attr('stroke-width', strokeWidth + 3);
        tooltip.style('opacity', '1')
          .html(`<strong>${source.label}</strong> → <strong>${target.label}</strong><br/>${edge.relationship}${source.risk_score ? `<br/>Risk Score: ${source.risk_score}` : ''}`)
          .style('left', `${event.pageX + 12}px`)
          .style('top', `${event.pageY - 30}px`);
      })
      .on('mousemove', function (event) {
        tooltip.style('left', `${event.pageX + 12}px`).style('top', `${event.pageY - 30}px`);
      })
      .on('mouseout', function () {
        d3.select(this).attr('opacity', 1).attr('stroke-width', strokeWidth);
        tooltip.style('opacity', '0');
      });
    });

    // Draw nodes
    allPositioned.forEach((node, i) => {
      const nx = (node as any).x;
      const ny = (node as any).y;
      const config = TYPE_CONFIG[node.type] || { color: '#94a3b8', icon: '?', tier: 1 };
      const nodeColor = node.risk_tier ? TIER_COLORS[node.risk_tier] : node.severity ? TIER_COLORS[node.severity] : config.color;
      const radius = node.type === 'organization' ? 32 : node.type === 'supplier' ? 24 : 20;

      const nodeG = g.append('g')
        .attr('transform', `translate(${nx},${ny})`)
        .style('cursor', 'pointer');

      // Glow effect for high-risk nodes
      if (node.risk_score && node.risk_score > 60) {
        nodeG.append('circle')
          .attr('r', radius + 8)
          .attr('fill', nodeColor)
          .attr('opacity', 0)
          .transition()
          .duration(1000)
          .delay(i * 40)
          .attr('opacity', 0.15);
      }

      // Main circle with animated entry
      nodeG.append('circle')
        .attr('r', 0)
        .attr('fill', nodeColor)
        .attr('stroke', 'white')
        .attr('stroke-width', 3)
        .transition()
        .duration(500)
        .delay(i * 40)
        .ease(d3.easeBackOut)
        .attr('r', radius);

      // Icon text
      nodeG.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '0.35em')
        .attr('fill', 'white')
        .attr('class', 'font-bold')
        .attr('font-size', `${radius * 0.6}px`)
        .attr('opacity', 0)
        .text(config.icon)
        .transition()
        .delay(i * 40 + 300)
        .duration(200)
        .attr('opacity', 1);

      // Label below
      nodeG.append('text')
        .attr('y', radius + 16)
        .attr('text-anchor', 'middle')
        .attr('class', 'text-[10px] font-medium fill-gray-700')
        .text(node.label.length > 20 ? node.label.slice(0, 18) + '...' : node.label);

      // Sub-label (risk score or severity)
      if (node.risk_score != null && node.risk_score > 0) {
        nodeG.append('text')
          .attr('y', radius + 28)
          .attr('text-anchor', 'middle')
          .attr('class', 'text-[9px] fill-gray-400')
          .text(`Risk: ${node.risk_score.toFixed(0)}/100`);
      } else if (node.severity) {
        nodeG.append('text')
          .attr('y', radius + 28)
          .attr('text-anchor', 'middle')
          .attr('class', 'text-[9px] fill-gray-400 capitalize')
          .text(node.severity);
      }

      // Hover
      nodeG.on('mouseover', function (event) {
        d3.select(this).select('circle:nth-child(2)').transition().duration(150).attr('r', radius * 1.2);
        let html = `<strong>${node.label}</strong><br/>Type: <span class="capitalize">${node.type}</span>`;
        if (node.risk_score != null) html += `<br/>Risk Score: <strong>${node.risk_score}/100</strong>`;
        if (node.risk_tier) html += `<br/>Tier: <span class="capitalize">${node.risk_tier}</span>`;
        if (node.severity) html += `<br/>Severity: <span class="capitalize">${node.severity}</span>`;
        if (node.region) html += `<br/>Region: ${node.country_code || ''} ${node.region}`;
        if (node.supplier_type) html += `<br/>Type: <span class="capitalize">${node.supplier_type.replace('_', ' ')}</span>`;
        tooltip.style('opacity', '1').html(html)
          .style('left', `${event.pageX + 14}px`).style('top', `${event.pageY - 30}px`);
      })
      .on('mousemove', function (event) {
        tooltip.style('left', `${event.pageX + 14}px`).style('top', `${event.pageY - 30}px`);
      })
      .on('mouseout', function () {
        d3.select(this).select('circle:nth-child(2)').transition().duration(150).attr('r', radius);
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
