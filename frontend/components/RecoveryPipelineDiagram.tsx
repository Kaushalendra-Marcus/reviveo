"use client";

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
  /** Precomputed anchor for the label pill, sitting directly on this connector's own path. */
  labelAt?: { x: number; y: number };
  marker?: boolean;
  pulseDelay?: number;
};

const PALETTE: Record<Category, { stroke: string; glow: string; fill: string; text: string }> = {
  blue: { stroke: "#2563eb", glow: "#60a5fa", fill: "#eff6ff", text: "#1d4ed8" },
  green: { stroke: "#16a34a", glow: "#4ade80", fill: "#ecfdf5", text: "#15803d" },
  amber: { stroke: "#d97706", glow: "#fbbf24", fill: "#fffbeb", text: "#b45309" },
  red: { stroke: "#dc2626", glow: "#f87171", fill: "#fef2f2", text: "#b91c1c" },
  purple: { stroke: "#7c3aed", glow: "#a78bfa", fill: "#f5f3ff", text: "#6d28d9" },
};

// ---------------------------------------------------------------------------
// Canvas + node geometry.
//
// Every box's height below is content-driven: it was computed from the
// title/subtitle/bullet copy via the same vertical-rhythm constants used in
// `computeContentLayout` further down, then given a small fixed buffer. This
// is what actually fixes the old "text overlapping the box below it" bug —
// short cards (Success, Execute Automatically, Failure, ...) used to reuse
// the same fixed offsets as the tall cards and overflowed their own box.
// If you edit any title/subtitle/bullets, re-check `h` still comfortably
// exceeds the box's rendered content (the dev console will not warn you).
// ---------------------------------------------------------------------------
export const PIPELINE_NODES: NodeConfig[] = [
  {
    id: "event", x: 24, y: 90, w: 158, h: 175,
    title: "Razorpay\nEvent",
    subtitle: "Payment failed / at-risk\nsubscription / webhook",
    icon: "bolt", category: "blue",
  },
  {
    id: "detect", x: 222, y: 90, w: 172, h: 172,
    title: "Detect",
    subtitle: "Capture real-time\npayment events and\nfailure signals",
    icon: "radar", category: "blue",
  },
  {
    id: "analyze", x: 434, y: 90, w: 162, h: 190,
    title: "Analyze",
    subtitle: "Classify root cause\nusing Razorpay error\ncodes and customer\nhistory",
    icon: "search", category: "blue",
  },
  {
    id: "decision", x: 646, y: 44, w: 254, h: 391,
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
    id: "guardrails", x: 940, y: 90, w: 196, h: 360,
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
    id: "execute", x: 1196, y: 90, w: 236, h: 154,
    title: "Execute Automatically",
    subtitle: "High confidence, within\nlimits — auto-approved",
    icon: "execute", category: "green",
  },
  {
    id: "human", x: 1196, y: 274, w: 236, h: 172,
    title: "Human Approval",
    subtitle: "Medium/low confidence\nor high amount —\nrequires review.",
    icon: "human", category: "amber",
  },
  {
    id: "blocked", x: 1196, y: 496, w: 236, h: 172,
    title: "Blocked Action",
    subtitle: "Action not allowed by\npolicy or rules —\nstopped & logged.",
    icon: "block", category: "red",
  },
  {
    id: "payment", x: 610, y: 496, w: 340, h: 172,
    title: "Payment Result",
    subtitle: "Tracks the outcome of the recovery attempt\nagainst the ORIGINAL failed payment —\nnot just any later payment from the customer.",
    icon: "payment", category: "blue",
  },
  {
    id: "success", x: 320, y: 530, w: 224, h: 172,
    title: "Success",
    subtitle: "Payment recovered successfully,\nlinked to original failed event\nand recovery window.",
    icon: "success", category: "green",
  },
  {
    id: "revenue", x: 320, y: 732, w: 224, h: 172,
    title: "Recovered Revenue",
    subtitle: "Revenue attributed back to the\nspecific recovery attempt that\ncaused it.",
    icon: "revenue", category: "green",
  },
  {
    id: "measure", x: 320, y: 934, w: 224, h: 190,
    title: "Measure & Attribute",
    subtitle: "Counted only if linked to the\noriginating event and within the\nrecovery window — never a raw\nsum of later payments.",
    icon: "measure", category: "green",
  },
  {
    id: "failure", x: 986, y: 716, w: 196, h: 154,
    title: "Failure",
    subtitle: "Recovery attempt did\nnot succeed.",
    icon: "failure", category: "red",
  },
  {
    id: "learn", x: 986, y: 900, w: 196, h: 172,
    title: "Explain & Learn",
    subtitle: "Root-cause explanation\nfeeds back into the audit\ntrail for review.",
    icon: "learn", category: "red",
  },
  {
    id: "audit", x: 1522, y: 450, w: 214, h: 720,
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

const CANVAS_W = 1776;
const CANVAS_H = 1220;

// Every path below is a clean orthogonal route between two node edges — none
// of them cut through a node they don't touch. The three fan-outs from
// Guardrails, the Human Approval outcomes, and the six Audit Trail feeds all
// travel through dedicated corridors beside the columns they pass, rather
// than the old diagonal/through-box shortcuts.
export const PIPELINE_CONNECTORS: ConnectorConfig[] = [
  { id: "c-event-detect", from: "event", to: "detect", d: "M182 177.5 L222 176", category: "blue", marker: true },
  { id: "c-detect-analyze", from: "detect", to: "analyze", d: "M394 176 L434 185", category: "blue", marker: true, pulseDelay: 0.2 },
  { id: "c-analyze-decision", from: "analyze", to: "decision", d: "M596 185 L646 185", category: "blue", marker: true, pulseDelay: 0.4 },
  { id: "c-decision-guard", from: "decision", to: "guardrails", d: "M900 270 L940 270", category: "blue", marker: true, pulseDelay: 0.6 },

  // guardrails fan-out — three distinct exit points down its right edge, one shared corridor
  { id: "c-guard-execute", from: "guardrails", to: "execute", d: "M1136 183.6 L1157.7 183.6 Q1166 183.6 1166 175.3 L1166 175.3 Q1166 167 1174.3 167 L1196 167", category: "green", marker: true },
  { id: "c-guard-human", from: "guardrails", to: "human", d: "M1136 280.8 L1156 280.8 Q1166 280.8 1166 290.8 L1166 350 Q1166 360 1176 360 L1196 360", category: "amber", marker: true, pulseDelay: 0.2 },
  { id: "c-guard-blocked", from: "guardrails", to: "blocked", d: "M1136 378 L1156 378 Q1166 378 1166 388 L1166 572 Q1166 582 1176 582 L1196 582", category: "red", marker: true, pulseDelay: 0.4 },

  // human approval's two outcomes
  {
    id: "c-human-denied", from: "human", to: "blocked",
    d: "M1365.92 446 L1365.92 461 Q1365.92 471 1355.92 471 L1262.64 471 Q1252.64 471 1252.64 481 L1252.64 496",
    category: "amber", marker: true, label: "Denied", labelAt: { x: 1309.28, y: 471 },
  },
  {
    id: "c-human-approved", from: "human", to: "payment",
    d: "M1432 342.8 L1452 342.8 Q1462 342.8 1462 352.8 L1462 686 Q1462 696 1452 696 L878.4 696 Q868.4 696 868.4 686 L868.4 668",
    category: "amber", marker: true, label: "Approved", labelAt: { x: 1225.2, y: 696 },
  },

  // execute / blocked outcomes
  { id: "c-execute-payment", from: "execute", to: "payment", d: "M1365.92 244 L1365.92 253 Q1365.92 262 1374.92 262 L1438 262 Q1448 262 1448 272 L1448 672 Q1448 682 1438 682 L814.2 682 Q807.2 682 807.2 675 L807.2 668", category: "green", marker: true },
  { id: "c-blocked-learn", from: "blocked", to: "learn", d: "M1262.08 668 L1262.08 941.6 Q1262.08 951.6 1252.08 951.6 L1182 951.6", category: "red", marker: true },

  // payment outcome branch
  { id: "c-payment-success", from: "payment", to: "success", d: "M610 556.2 L584 556.2 Q574 556.2 574 566.2 L574 606 Q574 616 564 616 L544 616", category: "green", marker: true },
  { id: "c-payment-failure", from: "payment", to: "failure", d: "M950 602.64 L1044.6 602.64 Q1054.6 602.64 1054.6 612.64 L1054.6 716", category: "red", marker: true },

  { id: "c-success-revenue", from: "success", to: "revenue", d: "M432 702 L432 732", category: "green", marker: true },
  { id: "c-revenue-measure", from: "revenue", to: "measure", d: "M432 904 L432 934", category: "green", marker: true },
  { id: "c-failure-learn", from: "failure", to: "learn", d: "M1084 870 L1084 900", category: "red", marker: true },

  // audit trail feeds — each on its own corridor into a distinct entry point on audit's left edge
  { id: "a-execute-audit", from: "execute", to: "audit", d: "M1432 194.72 L1468 194.72 Q1478 194.72 1478 204.72 L1478 476 Q1478 486 1488 486 L1522 486", category: "purple", audit: true },
  { id: "a-human-audit", from: "human", to: "audit", d: "M1432 390.96 L1482 390.96 Q1492 390.96 1492 400.96 L1492 540.8 Q1492 550.8 1502 550.8 L1522 550.8", category: "purple", audit: true, pulseDelay: 0.25 },
  { id: "a-blocked-audit", from: "blocked", to: "audit", d: "M1432 612.96 L1504.68 612.96 Q1506 612.96 1506 614.28 L1506 614.28 Q1506 615.6 1507.32 615.6 L1522 615.6", category: "purple", audit: true, pulseDelay: 0.5 },
  { id: "a-failure-audit", from: "failure", to: "audit", d: "M1182 808.4 L1482 808.4 Q1492 808.4 1492 818.4 L1492 915.2 Q1492 925.2 1502 925.2 L1522 925.2", category: "purple", audit: true, pulseDelay: 0.75 },
  { id: "a-learn-audit", from: "learn", to: "audit", d: "M1182 1003.2 L1473.8 1003.2 Q1478 1003.2 1478 1007.4 L1478 1007.4 Q1478 1011.6 1482.2 1011.6 L1522 1011.6", category: "purple", audit: true, pulseDelay: 1 },
  { id: "a-measure-audit", from: "measure", to: "audit", d: "M503.68 1124 L503.68 1142 Q503.68 1152 513.68 1152 L1468 1152 Q1478 1152 1478 1142 L1478 1136.8 Q1478 1126.8 1488 1126.8 L1522 1126.8", category: "purple", audit: true, pulseDelay: 1.25 },
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
    <g fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {iconPaths[type]}
    </g>
  );
}

function splitLines(value: string) {
  return value.split("\n");
}

// ---------------------------------------------------------------------------
// Dynamic content layout. This replaces the old fixed magic-number offsets
// (which assumed every card had the same number of title/subtitle lines and
// caused the "Amount / Risk Level" bullet to collide with the confidence
// sub-bullets above it, among other overlaps). Every vertical position below
// is derived from how much text actually precedes it, so a card can never
// overlap its own content regardless of how the copy changes later.
// ---------------------------------------------------------------------------
const ICON_BOTTOM = 56;
const GAP_ICON_TITLE = 22;
const TITLE_LINE_H = 21;
const GAP_TITLE_SUBTITLE = 18;
const SUBTITLE_LINE_H = 18;
const GAP_SUBTITLE_DIVIDER = 18;
const GAP_DIVIDER_BULLETS = 20;
const BULLET_ROW_H = 26;
const BULLET_TEXT_LINE_H = 15;
const BULLET_SUB_TOP_GAP = 17;
const BULLET_SUB_ROW_H = 19;
const BULLET_SUB_BOTTOM_GAP = 13;
const CONTENT_PAD_BOTTOM = 24;

function bulletBlockHeight(b: Bullet) {
  const lines = splitLines(b.text).length;
  const textExtra = (lines - 1) * BULLET_TEXT_LINE_H;
  if (b.sub && b.sub.length) {
    return BULLET_SUB_TOP_GAP + b.sub.length * BULLET_SUB_ROW_H + BULLET_SUB_BOTTOM_GAP;
  }
  return BULLET_ROW_H + textExtra;
}

function computeContentLayout(node: NodeConfig) {
  const titleLines = splitLines(node.title);
  const subtitleLines = splitLines(node.subtitle);

  const titleStartY = ICON_BOTTOM + GAP_ICON_TITLE;
  const titleEndY = titleStartY + (titleLines.length - 1) * TITLE_LINE_H;

  const subtitleStartY = titleEndY + GAP_TITLE_SUBTITLE;
  const subtitleEndY = subtitleStartY + (subtitleLines.length - 1) * SUBTITLE_LINE_H;

  let dividerY: number | null = null;
  const bulletRows: { bullet: Bullet; y: number }[] = [];
  let contentEndY = subtitleEndY;

  if (node.bullets && node.bullets.length) {
    dividerY = subtitleEndY + GAP_SUBTITLE_DIVIDER;
    let cursor = dividerY + GAP_DIVIDER_BULLETS;
    node.bullets.forEach((b) => {
      bulletRows.push({ bullet: b, y: cursor });
      cursor += bulletBlockHeight(b);
    });
    contentEndY = cursor - (BULLET_ROW_H - 12);
  }

  const minHeight = contentEndY + CONTENT_PAD_BOTTOM;

  return { titleLines, titleStartY, subtitleLines, subtitleStartY, dividerY, bulletRows, minHeight };
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
      opacity={dim ? 0.14 : connector.audit ? 0.55 : 0.95}
      style={{ transition: "opacity 180ms ease" }}
    >
      <path
        d={connector.d}
        fill="none"
        stroke={p.stroke}
        strokeWidth={connector.audit ? 1.7 : 2.4}
        strokeDasharray={connector.audit ? "3 7" : "9 7"}
        className={connector.audit ? "audit-flow" : "flow"}
        markerEnd={connector.marker ? `url(#arrow-${connector.category})` : undefined}
      />
      <path d={connector.d} fill="none" stroke={p.glow} strokeWidth={connector.audit ? 3 : 5} opacity="0.1" />
      {connector.label && connector.labelAt && (
        <g>
          <rect
            x={connector.labelAt.x - (connector.label.length * 3.6 + 12)}
            y={connector.labelAt.y - 13}
            width={connector.label.length * 7.2 + 24}
            height="26"
            rx="7"
            fill="white"
            stroke={p.stroke}
            opacity="0.98"
          />
          <text
            x={connector.labelAt.x}
            y={connector.labelAt.y + 4}
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
  isActive,
  isDimmed,
  setActiveNode,
}: {
  node: NodeConfig;
  index: number;
  isActive: boolean;
  isDimmed: boolean;
  setActiveNode: (id: string | null) => void;
}) {
  const p = PALETTE[node.category];
  const layout = computeContentLayout(node);
  const extra = Math.max(0, node.h - layout.minHeight);
  const vOffset = extra / 2; // center content within any extra room the box has (e.g. Audit Trail's tall span)
  const hasBullets = Boolean(node.bullets?.length);
  const cx = node.x + node.w / 2;

  return (
    <motion.g
      initial={{ opacity: 0, scale: 0.94 }}
      whileInView={{ opacity: 1, scale: isActive ? 1.02 : 1 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ delay: index * 0.06, duration: 0.45, type: "spring", stiffness: 220, damping: 22 }}
      onMouseEnter={() => setActiveNode(node.id)}
      onMouseLeave={() => setActiveNode(null)}
      onFocus={() => setActiveNode(node.id)}
      onBlur={() => setActiveNode(null)}
      opacity={isDimmed ? 0.35 : 1}
      style={{ transformOrigin: `${cx}px ${node.y + node.h / 2}px`, cursor: "pointer" }}
      tabIndex={0}
    >
      <rect
        x={node.x}
        y={node.y}
        width={node.w}
        height={node.h}
        rx={node.rounded ?? 16}
        fill="rgba(255,255,255,0.97)"
        stroke={isActive || node.highlighted ? "#93c5fd" : "#e2e8f0"}
        strokeWidth={isActive || node.highlighted ? 1.75 : 1.25}
        filter={node.highlighted || isActive ? "url(#card-glow)" : "url(#soft-shadow)"}
      />
      <rect
        x={node.x + 1}
        y={node.y + 1}
        width={node.w - 2}
        height={node.h - 2}
        rx={(node.rounded ?? 16) - 1}
        fill="url(#card-sheen)"
        opacity="0.5"
        pointerEvents="none"
      />

      <circle cx={cx} cy={node.y + 36 + vOffset} r="20" fill={p.fill} opacity="0.9" />
      <g transform={`translate(${cx - 12} ${node.y + 24 + vOffset})`}>
        <Icon type={node.icon} color={p.stroke} />
      </g>

      <text
        x={cx}
        y={node.y + layout.titleStartY + vOffset}
        textAnchor="middle"
        fontSize={node.id === "decision" ? 18 : 17}
        fontWeight="750"
        fill={node.category === "purple" ? p.text : "#172554"}
      >
        {layout.titleLines.map((line, i) => (
          <tspan key={i} x={cx} dy={i === 0 ? 0 : TITLE_LINE_H}>
            {line}
          </tspan>
        ))}
      </text>

      <text
        x={cx}
        y={node.y + layout.subtitleStartY + vOffset}
        textAnchor="middle"
        fontSize="12.5"
        fontWeight="500"
        fill="#475569"
      >
        {layout.subtitleLines.map((line, i) => (
          <tspan key={i} x={cx} dy={i === 0 ? 0 : SUBTITLE_LINE_H}>
            {line}
          </tspan>
        ))}
      </text>

      {hasBullets && layout.dividerY !== null && (
        <>
          <line
            x1={node.x + 16}
            x2={node.x + node.w - 16}
            y1={node.y + layout.dividerY + vOffset}
            y2={node.y + layout.dividerY + vOffset}
            stroke="#e2e8f0"
          />
          {layout.bulletRows.map(({ bullet, y }) => (
            <g key={bullet.text} transform={`translate(${node.x + 26} ${node.y + y + vOffset})`}>
              <circle cx="0" cy="0" r="6" fill={p.fill} stroke={p.stroke} strokeWidth="1" />
              <path d="m-2 0 1.5 1.7L3-2" fill="none" stroke={p.stroke} strokeWidth="1.5" strokeLinecap="round" />
              <text x="16" y="4" fontSize="12.5" fontWeight="600" fill="#334155">
                {splitLines(bullet.text).map((line, li) => (
                  <tspan key={li} x="16" dy={li === 0 ? 0 : BULLET_TEXT_LINE_H}>{line}</tspan>
                ))}
              </text>
              {bullet.sub?.map((s, j) => {
                const sp = PALETTE[s.tone];
                return (
                  <g key={s.text} transform={`translate(24 ${BULLET_SUB_TOP_GAP + j * BULLET_SUB_ROW_H})`}>
                    <circle cx="0" cy="0" r="3.5" fill={sp.stroke} />
                    <text x="12" y="4" fontSize="11.5" fontWeight="650" fill="#475569">{s.text}</text>
                  </g>
                );
              })}
            </g>
          ))}
        </>
      )}
    </motion.g>
  );
}

export default function RecoveryPipelineDiagram() {
  const [activeNode, setActiveNode] = useState<string | null>(null);

  const connectedNodeIds = useMemo(() => {
    if (!activeNode) return null;
    const ids = new Set<string>([activeNode]);
    PIPELINE_CONNECTORS.forEach((c) => {
      if (c.from === activeNode) ids.add(c.to);
      if (c.to === activeNode) ids.add(c.from);
    });
    return ids;
  }, [activeNode]);

  return (
    <section className="relative w-full overflow-hidden bg-slate-50 py-16 sm:py-24">
      <style>{`
        .flow { animation: reviveo-flow 1.8s linear infinite; }
        .audit-flow { animation: reviveo-audit-flow 4.5s linear infinite; }
        @keyframes reviveo-flow { to { stroke-dashoffset: -32; } }
        @keyframes reviveo-audit-flow { to { stroke-dashoffset: -20; } }
      `}</style>

      <div className="mx-auto max-w-3xl px-6 text-center lg:px-8">
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-700">The recovery engine</p>
        <h2 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
          From failed payment to recovered revenue.
        </h2>
        <p className="mt-4 text-base leading-7 text-slate-600">
          Hover any step to trace exactly how Reviveo moves a payment through detection,
          the decision engine, guardrails, and the audit trail.
        </p>
      </div>

      <div className="mx-auto mt-12 max-w-[1820px] px-3 sm:px-6 lg:px-8">
        <div className="relative overflow-x-auto rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="min-w-[1320px] p-4 sm:p-6">
            <svg
              viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
              width="100%"
              role="img"
              aria-label="Reviveo AI Revenue Recovery Agent architecture flow"
              preserveAspectRatio="xMidYMid meet"
              className="block h-auto min-w-[1320px] select-none"
            >
              <defs>
                <linearGradient id="card-sheen" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="#ffffff" />
                  <stop offset="1" stopColor="#f8fafc" stopOpacity="0.15" />
                </linearGradient>
                <filter id="soft-shadow" x="-20%" y="-20%" width="140%" height="150%">
                  <feDropShadow dx="0" dy="8" stdDeviation="10" floodColor="#0f172a" floodOpacity="0.07" />
                </filter>
                <filter id="card-glow" x="-30%" y="-30%" width="160%" height="160%">
                  <feDropShadow dx="0" dy="0" stdDeviation="8" floodColor="#2563eb" floodOpacity="0.16" />
                  <feDropShadow dx="0" dy="12" stdDeviation="16" floodColor="#0f172a" floodOpacity="0.08" />
                </filter>
                {Object.entries(PALETTE).map(([key, value]) => (
                  <React.Fragment key={key}>
                    <filter id={`glow-${key}`} x="-400%" y="-400%" width="800%" height="800%">
                      <feGaussianBlur stdDeviation="3" result="blur" />
                      <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                    </filter>
                    <marker id={`arrow-${key}`} markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">
                      <path d="M0,0 L8,4.5 L0,9 Z" fill={value.stroke} />
                    </marker>
                  </React.Fragment>
                ))}
                <pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse">
                  <path d="M44 0H0V44" fill="none" stroke="#dbe5f3" strokeOpacity="0.22" />
                </pattern>
              </defs>

              <rect x="0" y="0" width={CANVAS_W} height={CANVAS_H} fill="url(#grid)" opacity="0.6" />
              <circle cx="870" cy="290" r="320" fill="#dbeafe" opacity="0.16" />
              <circle cx="1500" cy="360" r="240" fill="#ede9fe" opacity="0.12" />
              <circle cx="420" cy="820" r="280" fill="#dcfce7" opacity="0.10" />

              {/* connectors render behind nodes */}
              {PIPELINE_CONNECTORS.map((connector) => (
                <AnimatedConnector key={connector.id} connector={connector} activeNode={activeNode} />
              ))}

              {PIPELINE_NODES.map((node, index) => (
                <NodeCard
                  key={node.id}
                  node={node}
                  index={index}
                  isActive={activeNode === node.id}
                  isDimmed={Boolean(activeNode) && !(connectedNodeIds?.has(node.id) ?? false)}
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
