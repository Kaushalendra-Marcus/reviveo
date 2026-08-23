import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";

type Category = "blue" | "green" | "amber" | "red" | "purple";

type Bullet = {
  text: string;
  sub?: { text: string; tone: "green" | "amber" | "red" }[];
};

type NodeConfig = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  subtitle: string;
  icon:
    | "bolt"
    | "radar"
    | "search"
    | "brain"
    | "shield"
    | "execute"
    | "human"
    | "block"
    | "payment"
    | "success"
    | "revenue"
    | "measure"
    | "failure"
    | "learn"
    | "audit";
  category: Category;
  bullets?: Bullet[];
  highlighted?: boolean;
  rounded?: number;
};

type ConnectorConfig = {
  id: string;
  from: string;
  to: string;
  d: string;
  category: Category;
  audit?: boolean;
  label?: string;
  marker?: boolean;
  pulseDelay?: number;
};

const PALETTE: Record<Category, { stroke: string; glow: string; fill: string; text: string }> = {
  blue: {
    stroke: "#2563eb",
    glow: "#60a5fa",
    fill: "#eff6ff",
    text: "#1d4ed8",
  },
  green: {
    stroke: "#16a34a",
    glow: "#4ade80",
    fill: "#ecfdf5",
    text: "#15803d",
  },
  amber: {
    stroke: "#d97706",
    glow: "#fbbf24",
    fill: "#fffbeb",
    text: "#b45309",
  },
  red: {
    stroke: "#dc2626",
    glow: "#f87171",
    fill: "#fef2f2",
    text: "#b91c1c",
  },
  purple: {
    stroke: "#7c3aed",
    glow: "#a78bfa",
    fill: "#f5f3ff",
    text: "#6d28d9",
  },
};

export const PIPELINE_NODES: NodeConfig[] = [
  {
    id: "event", x: 18, y: 80, w: 150, h: 205,
    title: "Razorpay\nEvent",
    subtitle: "Payment failed / at-risk\nsubscription / webhook",
    icon: "bolt", category: "blue",
  },
  {
    id: "detect", x: 215, y: 80, w: 165, h: 205,
    title: "Detect",
    subtitle: "Capture real-time\npayment events and\nfailure signals",
    icon: "radar", category: "blue",
  },
  {
    id: "analyze", x: 430, y: 80, w: 155, h: 205,
    title: "Analyze",
    subtitle: "Classify root cause\nusing Razorpay error\ncodes and customer\nhistory",
    icon: "search", category: "blue",
  },
  {
    id: "decision", x: 650, y: 30, w: 250, h: 395,
    title: "AI Decision Engine",
    subtitle: "Evaluates and decides the best\nrecovery action, bounded by\nrule-engine policy.",
    icon: "brain", category: "blue", highlighted: true,
    bullets: [
      { text: "Root Cause Analysis" },
      { text: "Payment History" },
      { text: "Customer Context" },
      {
        text: "Confidence Score",
        sub: [
          { text: "High ≥ 85%", tone: "green" },
          { text: "Medium 50–85%", tone: "amber" },
          { text: "Low < 50%", tone: "red" },
        ],
      },
      { text: "Amount / Risk Level" },
    ],
  },
  {
    id: "guardrails", x: 935, y: 80, w: 190, h: 335,
    title: "Guardrails",
    subtitle: "Enforces safety limits — the\nAI proposes, guardrails have\nfinal authority to block.",
    icon: "shield", category: "blue",
    bullets: [
      { text: "Policy-defined action\nwhitelist" },
      { text: "Retry & cooldown limits" },
      { text: "Confidence thresholds" },
      { text: "Daily & per-action\nspend limits" },
      { text: "Customer contact caps" },
    ],
  },
  {
    id: "execute", x: 1185, y: 78, w: 230, h: 105,
    title: "Execute Automatically",
    subtitle: "High confidence, within\nlimits — auto-approved",
    icon: "execute", category: "green",
  },
  {
    id: "human", x: 1185, y: 220, w: 230, h: 110,
    title: "Human Approval",
    subtitle: "Medium/low confidence\nor high amount —\nrequires review.",
    icon: "human", category: "amber",
  },
  {
    id: "blocked", x: 1185, y: 385, w: 230, h: 110,
    title: "Blocked Action",
    subtitle: "Action not allowed by\npolicy or rules —\nstopped & logged.",
    icon: "block", category: "red",
  },
  {
    id: "payment", x: 610, y: 485, w: 340, h: 105,
    title: "Payment Result",
    subtitle: "Tracks the outcome of the recovery attempt\nagainst the ORIGINAL failed payment —\nnot just any later payment from the customer.",
    icon: "payment", category: "blue",
  },
  {
    id: "success", x: 315, y: 565, w: 220, h: 95,
    title: "Success",
    subtitle: "Payment recovered successfully,\nlinked to original failed event\nand recovery window.",
    icon: "success", category: "green",
  },
  {
    id: "revenue", x: 315, y: 680, w: 220, h: 95,
    title: "Recovered Revenue",
    subtitle: "Revenue attributed back to the\nspecific recovery attempt that\ncaused it.",
    icon: "revenue", category: "green",
  },
  {
    id: "measure", x: 315, y: 795, w: 220, h: 115,
    title: "Measure & Attribute",
    subtitle: "Counted only if linked to the\noriginating event and within the\nrecovery window — never a raw\nsum of later payments.",
    icon: "measure", category: "green",
  },
  {
    id: "failure", x: 975, y: 585, w: 170, h: 90,
    title: "Failure",
    subtitle: "Recovery attempt did\nnot succeed.",
    icon: "failure", category: "red",
  },
  {
    id: "learn", x: 975, y: 710, w: 190, h: 105,
    title: "Explain & Learn",
    subtitle: "Root-cause explanation\nfeeds back into the audit\ntrail for review.",
    icon: "learn", category: "red",
  },
  {
    id: "audit", x: 1455, y: 375, w: 210, h: 520,
    title: "Audit Trail",
    subtitle: "Every decision, action, and\noutcome is recorded —\nnothing bypasses this.",
    icon: "audit", category: "purple",
    bullets: [
      { text: "Full Decision Logs" },
      { text: "Action Taken" },
      { text: "Approvals\n(incl. who/when)" },
      { text: "Outcomes\n(linked to original event)" },
      { text: "Timestamps & Latency" },
    ],
    rounded: 18,
  },
];

export const PIPELINE_CONNECTORS: ConnectorConfig[] = [
  { id: "c-event-detect", from: "event", to: "detect", d: "M168 182 H215", category: "blue", marker: true },
  { id: "c-detect-analyze", from: "detect", to: "analyze", d: "M380 182 H430", category: "blue", marker: true, pulseDelay: 0.2 },
  { id: "c-analyze-decision", from: "analyze", to: "decision", d: "M585 182 H620 Q635 182 650 182", category: "blue", marker: true, pulseDelay: 0.4 },
  { id: "c-decision-guard", from: "decision", to: "guardrails", d: "M900 220 H935", category: "blue", marker: true, pulseDelay: 0.6 },

  { id: "c-guard-execute", from: "guardrails", to: "execute", d: "M1125 165 H1155 Q1168 165 1168 150 V130 Q1168 120 1185 120", category: "green", marker: true },
  { id: "c-guard-human", from: "guardrails", to: "human", d: "M1125 235 H1155 Q1168 235 1168 275 H1185", category: "amber", marker: true, pulseDelay: 0.2 },
  { id: "c-guard-blocked", from: "guardrails", to: "blocked", d: "M1125 345 H1160 Q1170 345 1170 440 H1185", category: "red", marker: true, pulseDelay: 0.4 },

  { id: "c-human-approved", from: "human", to: "payment", d: "M1415 275 H1490 V125 H1450 V455 Q1450 455 1435 455 H980 Q965 455 950 520", category: "amber", label: "Approved", marker: true },
  { id: "c-human-denied", from: "human", to: "blocked", d: "M1300 330 V360 Q1300 372 1300 385", category: "amber", label: "Denied", marker: true },

  { id: "c-execute-payment", from: "execute", to: "payment", d: "M1300 183 V445 Q1300 455 1288 455 H970 Q950 455 950 485", category: "green", marker: true },
  { id: "c-blocked-learn", from: "blocked", to: "learn", d: "M1300 495 V550 H1210 Q1190 550 1190 575 V710 H1165", category: "red", marker: true },

  { id: "c-payment-success", from: "payment", to: "success", d: "M610 535 H560 Q545 535 545 565 H535", category: "green", marker: true },
  { id: "c-success-revenue", from: "success", to: "revenue", d: "M425 660 V680", category: "green", marker: true },
  { id: "c-revenue-measure", from: "revenue", to: "measure", d: "M425 775 V795", category: "green", marker: true },

  { id: "c-payment-failure", from: "payment", to: "failure", d: "M950 540 H990 Q1005 540 1005 585", category: "red", marker: true },
  { id: "c-failure-learn", from: "failure", to: "learn", d: "M1060 675 V710", category: "red", marker: true },

  // Distinct secondary logging feeds into unique vertical entry points on Audit Trail.
  { id: "a-execute-audit", from: "execute", to: "audit", d: "M1415 130 H1525 V405 H1455", category: "purple", audit: true },
  { id: "a-human-audit", from: "human", to: "audit", d: "M1415 275 H1510 V485 H1455", category: "purple", audit: true, pulseDelay: 0.25 },
  { id: "a-blocked-audit", from: "blocked", to: "audit", d: "M1415 440 H1455", category: "purple", audit: true, pulseDelay: 0.5 },
  { id: "a-failure-audit", from: "failure", to: "audit", d: "M1145 630 H1380 Q1400 630 1400 610 H1455", category: "purple", audit: true, pulseDelay: 0.75 },
  { id: "a-learn-audit", from: "learn", to: "audit", d: "M1165 760 H1400 Q1420 760 1420 700 H1455", category: "purple", audit: true, pulseDelay: 1 },
  { id: "a-measure-audit", from: "measure", to: "audit", d: "M535 852 H1415 Q1430 852 1430 790 H1455", category: "purple", audit: true, pulseDelay: 1.25 },
];

const iconPaths: Record<NodeConfig["icon"], React.ReactNode> = {
  bolt: <path d="M14 2 5 14h7l-2 8 9-12h-7l2-8Z" />,
  radar: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><path d="M12 2v2M22 12h-2M12 22v-2M2 12h2M18.5 5.5l-1.4 1.4M5.5 18.5l1.4-1.4M18.5 18.5l-1.4-1.4M5.5 5.5l1.4 1.4" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  brain: <><path d="M9 4a3 3 0 0 0-5 2.2A3.5 3.5 0 0 0 5.5 13 3 3 0 0 0 9 18h1V4H9ZM15 4a3 3 0 0 1 5 2.2A3.5 3.5 0 0 1 18.5 13 3 3 0 0 1 15 18h-1V4h1Z" /><path d="M10 7H7M14 7h3M10 11H6M14 11h4M12 4v15" /></>,
  shield: <path d="M12 3 20 6v5c0 5-3.4 8.3-8 10-4.6-1.7-8-5-8-10V6l8-3Zm-3 9 2 2 4-5" />,
  execute: <path d="m14 2-9 12h6l-1 8 9-12h-6l1-8Z" />,
  human: <><circle cx="12" cy="7" r="4" /><path d="M4 22c.6-5 3.2-8 8-8s7.4 3 8 8" /></>,
  block: <><path d="M12 3v9M8.5 6.5 12 3l3.5 3.5" /><path d="M5 12v6a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3v-6" /></>,
  payment: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 9h18M17 14h1" /></>,
  success: <path d="m5 12 4 4L19 6" />,
  revenue: <><path d="M4 19V9M9 19V13M14 19V6M19 19V3" /><path d="m4 12 5-4 4 2 7-6" /></>,
  measure: <><path d="M12 3a9 9 0 1 0 9 9h-9V3Z" /><path d="M14 3.3A9 9 0 0 1 20.7 10H14V3.3Z" /></>,
  failure: <><circle cx="12" cy="12" r="9" /><path d="m9 9 6 6m0-6-6 6" /></>,
  learn: <><path d="M9 21h6M10 18h4" /><path d="M8 15a6 6 0 1 1 8 0c-1.1 1-1.5 1.8-1.5 3h-5c0-1.2-.4-2-1.5-3Z" /></>,
  audit: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 3V1h6v2M8 10h8M8 14h5M14 17l1.5 1.5L19 15" /></>,
};

function Icon({ type, color }: { type: NodeConfig["icon"]; color: string }) {
  return (
    <g transform="translate(0 0)" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {iconPaths[type]}
    </g>
  );
}

function splitLines(value: string) {
  return value.split("\n");
}

function AnimatedConnector({
  connector,
  activeNode,
}: {
  connector: ConnectorConfig;
  activeNode: string | null;
}) {
  const p = PALETTE[connector.category];
  const active = !activeNode || connector.from === activeNode || connector.to === activeNode;
  const dim = activeNode && !active;

  return (
    <g
      className={connector.audit ? "audit-connector" : "connector"}
      opacity={dim ? 0.16 : connector.audit ? 0.58 : 0.95}
      style={{ transition: "opacity 180ms ease" }}
    >
      <path
        d={connector.d}
        fill="none"
        stroke={p.stroke}
        strokeWidth={connector.audit ? 1.7 : 2.4}
        strokeDasharray={connector.audit ? "3 7" : "10 8"}
        className={connector.audit ? "audit-flow" : "flow"}
        markerEnd={connector.marker ? `url(#arrow-${connector.category})` : undefined}
      />
      <path d={connector.d} fill="none" stroke={p.glow} strokeWidth={connector.audit ? 3 : 5} opacity="0.1" />
      {connector.label && (
        <g>
          <rect
            x={connector.id === "c-human-approved" ? 1422 : 1275}
            y={connector.id === "c-human-approved" ? 245 : 355}
            width={connector.id === "c-human-approved" ? 64 : 58}
            height="26"
            rx="7"
            fill="white"
            stroke={p.stroke}
            opacity="0.98"
          />
          <text
            x={connector.id === "c-human-approved" ? 1454 : 1304}
            y={connector.id === "c-human-approved" ? 262 : 372}
            textAnchor="middle"
            fontSize="12"
            fontWeight="700"
            fill={p.text}
          >
            {connector.label}
          </text>
        </g>
      )}
      <circle r={connector.audit ? 3 : 4} fill={p.glow} filter={`url(#glow-${connector.category})`} opacity={connector.audit ? 0.7 : 1}>
        <animateMotion dur={connector.audit ? "4.5s" : "1.8s"} begin={`${connector.pulseDelay ?? 0}s`} repeatCount="indefinite">
          <mpath href={`#path-${connector.id}`} />
        </animateMotion>
      </circle>
      <path id={`path-${connector.id}`} d={connector.d} fill="none" stroke="none" />
    </g>
  );
}

function NodeCard({
  node,
  index,
  activeNode,
  setActiveNode,
}: {
  node: NodeConfig;
  index: number;
  activeNode: string | null;
  setActiveNode: (id: string | null) => void;
}) {
  const p = PALETTE[node.category];
  const dim = activeNode && activeNode !== node.id;
  const lines = splitLines(node.title);
  const bulletStart = node.id === "decision" ? node.y + 205 : node.y + 190;
  const hasBullets = Boolean(node.bullets?.length);

  return (
    <motion.g
      initial={{ opacity: 0, scale: 0.94 }}
      whileInView={{ opacity: 1, scale: activeNode === node.id ? 1.02 : 1 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{
        delay: index * 0.09,
        duration: 0.45,
        type: "spring",
        stiffness: 220,
        damping: 22,
      }}
      onMouseEnter={() => setActiveNode(node.id)}
      onMouseLeave={() => setActiveNode(null)}
      onFocus={() => setActiveNode(node.id)}
      onBlur={() => setActiveNode(null)}
      opacity={dim ? 0.38 : 1}
      style={{ transformOrigin: `${node.x + node.w / 2}px ${node.y + node.h / 2}px`, cursor: "pointer" }}
    >
      <rect
        x={node.x}
        y={node.y}
        width={node.w}
        height={node.h}
        rx={node.rounded ?? 16}
        fill="rgba(255,255,255,0.96)"
        stroke={activeNode === node.id || node.highlighted ? p.stroke : "#d5ddeb"}
        strokeWidth={activeNode === node.id || node.highlighted ? 2 : 1.25}
        filter={node.highlighted || activeNode === node.id ? "url(#card-glow)" : "url(#soft-shadow)"}
      />
      <rect
        x={node.x + 1}
        y={node.y + 1}
        width={node.w - 2}
        height={node.h - 2}
        rx={(node.rounded ?? 16) - 1}
        fill="url(#card-sheen)"
        opacity="0.55"
        pointerEvents="none"
      />

      <g transform={`translate(${node.x + node.w / 2 - 16} ${node.y + 20})`}>
        <circle cx="16" cy="16" r="20" fill={p.fill} opacity="0.9" />
        <g transform="translate(4 4) scale(1.15)">
          <Icon type={node.icon} color={p.stroke} />
        </g>
      </g>

      <text
        x={node.x + node.w / 2}
        y={node.y + (lines.length > 1 ? 98 : 98)}
        textAnchor="middle"
        fontSize={node.id === "decision" ? 18 : 17}
        fontWeight="750"
        fill={node.category === "purple" ? p.text : "#172554"}
      >
        {lines.map((line, i) => (
          <tspan key={line + i} x={node.x + node.w / 2} dy={i === 0 ? 0 : 20}>
            {line}
          </tspan>
        ))}
      </text>

      <text
        x={node.x + node.w / 2}
        y={node.y + (lines.length > 1 ? 146 : 126)}
        textAnchor="middle"
        fontSize="12.5"
        fontWeight="500"
        fill="#475569"
      >
        {splitLines(node.subtitle).map((line, i) => (
          <tspan key={line + i} x={node.x + node.w / 2} dy={i === 0 ? 0 : 18}>
            {line}
          </tspan>
        ))}
      </text>

      {hasBullets && (
        <>
          <line
            x1={node.x + 16}
            x2={node.x + node.w - 16}
            y1={node.id === "decision" ? node.y + 195 : node.y + 178}
            y2={node.id === "decision" ? node.y + 195 : node.y + 178}
            stroke="#e2e8f0"
          />
          <g transform={`translate(${node.x + 26} ${bulletStart})`}>
            {node.bullets!.map((bullet, i) => {
              const previousSub = node.bullets!.slice(0, i).reduce((sum, b) => sum + (b.sub ? 38 : 0), 0);
              const yy = i * 31 + previousSub;
              return (
                <g key={bullet.text} transform={`translate(0 ${yy})`}>
                  <circle cx="0" cy="0" r="6" fill={p.fill} stroke={p.stroke} strokeWidth="1" />
                  <path d="m-2 0 1.5 1.7L3-2" fill="none" stroke={p.stroke} strokeWidth="1.5" strokeLinecap="round" />
                  <text x="16" y="4" fontSize="12.5" fontWeight="600" fill="#334155">
                    {splitLines(bullet.text).map((line, lineIndex) => (
                      <tspan key={line} x="16" dy={lineIndex === 0 ? 0 : 15}>{line}</tspan>
                    ))}
                  </text>
                  {bullet.sub?.map((s, j) => {
                    const sp = PALETTE[s.tone];
                    return (
                      <g key={s.text} transform={`translate(24 ${18 + j * 21})`}>
                        <circle cx="0" cy="0" r="3.5" fill={sp.stroke} />
                        <text x="12" y="4" fontSize="11.5" fontWeight="650" fill="#475569">{s.text}</text>
                      </g>
                    );
                  })}
                </g>
              );
            })}
          </g>
        </>
      )}
    </motion.g>
  );
}

export default function RecoveryPipelineDiagram() {
  const [activeNode, setActiveNode] = useState<string | null>(null);

  const connectedNodeIds = useMemo(() => {
    if (!activeNode) return new Set<string>();
    return new Set([
      activeNode,
      ...PIPELINE_CONNECTORS
        .filter((c) => c.from === activeNode || c.to === activeNode)
        .flatMap((c) => [c.from, c.to]),
    ]);
  }, [activeNode]);

  return (
    <section className="relative w-full overflow-hidden bg-[#f7f9fd] py-8 sm:py-12">
      <style>{`
        .flow { animation: reviveo-flow 1.8s linear infinite; }
        .audit-flow { animation: reviveo-audit-flow 4.5s linear infinite; }
        @keyframes reviveo-flow { to { stroke-dashoffset: -36; } }
        @keyframes reviveo-audit-flow { to { stroke-dashoffset: -28; } }
      `}</style>

      <div className="mx-auto max-w-[1800px] px-3 sm:px-6 lg:px-8">
        <div className="relative overflow-x-auto rounded-3xl border border-slate-200/80 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.10)]">
          <div className="min-w-[1280px] p-2 sm:p-4">
            <svg
              viewBox="0 0 1700 950"
              width="100%"
              role="img"
              aria-label="Reviveo AI Revenue Recovery Agent architecture flow"
              preserveAspectRatio="xMidYMid meet"
              className="block h-auto min-w-[1280px] select-none"
              style={{ background: "radial-gradient(circle at 48% 35%, #ffffff 0%, #f7f9fd 58%, #eef3fb 100%)" }}
            >
              <defs>
                <linearGradient id="card-sheen" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="#ffffff" />
                  <stop offset="1" stopColor="#f8fafc" stopOpacity="0.15" />
                </linearGradient>
                <filter id="soft-shadow" x="-20%" y="-20%" width="140%" height="150%">
                  <feDropShadow dx="0" dy="10" stdDeviation="12" floodColor="#0f172a" floodOpacity="0.08" />
                </filter>
                <filter id="card-glow" x="-30%" y="-30%" width="160%" height="160%">
                  <feDropShadow dx="0" dy="0" stdDeviation="9" floodColor="#2563eb" floodOpacity="0.22" />
                  <feDropShadow dx="0" dy="14" stdDeviation="18" floodColor="#0f172a" floodOpacity="0.10" />
                </filter>
                {Object.entries(PALETTE).map(([key, value]) => (
                  <React.Fragment key={key}>
                    <filter id={`glow-${key}`} x="-400%" y="-400%" width="800%" height="800%">
                      <feGaussianBlur stdDeviation="3" result="blur" />
                      <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                    </filter>
                    <marker
                      id={`arrow-${key}`}
                      markerWidth="9"
                      markerHeight="9"
                      refX="7"
                      refY="4.5"
                      orient="auto"
                      markerUnits="userSpaceOnUse"
                    >
                      <path d="M0,0 L8,4.5 L0,9 Z" fill={value.stroke} />
                    </marker>
                  </React.Fragment>
                ))}
                <pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse">
                  <path d="M44 0H0V44" fill="none" stroke="#dbe5f3" strokeOpacity="0.22" />
                </pattern>
              </defs>

              <rect x="0" y="0" width="1700" height="950" fill="url(#grid)" opacity="0.7" />
              <circle cx="830" cy="430" r="290" fill="#dbeafe" opacity="0.18" />
              <circle cx="1320" cy="250" r="220" fill="#ede9fe" opacity="0.12" />
              <circle cx="400" cy="730" r="260" fill="#dcfce7" opacity="0.10" />

              {/* connectors render behind nodes */}
              {PIPELINE_CONNECTORS.map((connector) => (
                <AnimatedConnector
                  key={connector.id}
                  connector={connector}
                  activeNode={activeNode}
                />
              ))}

              {PIPELINE_NODES.map((node, index) => (
                <NodeCard
                  key={node.id}
                  node={node}
                  index={index}
                  activeNode={activeNode && connectedNodeIds.has(node.id) ? activeNode : activeNode}
                  setActiveNode={setActiveNode}
                />
              ))}
            </svg>
          </div>
        </div>
      </div>
    </section>
  );
}
