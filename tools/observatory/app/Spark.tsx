'use client';
import { useEffect, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';
import { dayAt, dayBox, fmtValue, tickFormat, xOf, xRange } from '../src/chart';
import type { Mark } from '../src/chart';

export type SparkProps = {
  dates: string[];
  unit: string;
  lines: { label: string; data: (number | null)[]; color: string }[];
  band?: { lo: (number | null)[]; hi: (number | null)[] };
  grey?: boolean[]; // low-n days, shaded
  marks?: Mark[]; // harness commits, vertical lines
  tips: string[][]; // one tooltip per day
  markTips?: string[]; // one tooltip per mark
  reference?: { value: number; label: string }; // dashed median line
  yRange?: [number, number];
  height?: number;
};

const axis = { stroke: '#5f6368', grid: { stroke: 'rgba(0,0,0,0.08)', width: 1 } };

export default function Spark({ dates, unit, lines, band, grey, marks, tips, markTips, reference, yRange, height = 160 }: SparkProps) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const x = dates.map(xOf);
    const data: uPlot.AlignedData = [x, ...lines.map((l) => l.data), ...(band ? [band.lo, band.hi] : [])];
    const n = lines.length;
    const series: uPlot.Series[] = [
      {},
      ...lines.map((l) => ({ label: l.label, stroke: l.color, width: 2, spanGaps: false, points: { show: false } })),
      ...(band ? [{ label: 'p25', stroke: 'transparent', points: { show: false } }, { label: 'p75', stroke: 'transparent', points: { show: false } }] : []),
    ];
    const tip = document.createElement('div');
    tip.className = 'pointer-events-none absolute z-10 hidden rounded bg-surface px-2 py-1 text-xs text-on-surface shadow-e2';
    const setTip = (lines: string[]) => {
      tip.replaceChildren(...lines.flatMap((t, i) => (i ? [document.createElement('br'), document.createTextNode(t)] : [document.createTextNode(t)])));
    };

    const plot = new uPlot(
      {
        width: el.current!.clientWidth, height, legend: { show: false },
        tzDate: (ts) => uPlot.tzDate(new Date(ts * 1e3), 'UTC'),
        cursor: { points: { show: true }, drag: { x: false, y: false }, dataIdx: (_u, _s, _c, xv) => dayAt(xv, x[0]!, dates.length) },
        scales: { x: { time: true, range: () => xRange(dates) }, y: yRange ? { range: () => yRange } : {} },
        axes: [
          { ...axis, values: tickFormat(dates.length) },
          { ...axis, space: 30, values: (_u, ts) => ts.map((v) => fmtValue(v, unit)) },
        ],
        padding: [8, 8, 0, 0],
        series,
        bands: band ? [{ series: [n + 2, n + 1], fill: 'rgba(21,101,192,0.15)' }] : [],
        hooks: {
          init: [(u) => { u.over.appendChild(tip); }],
          setCursor: [(u) => {
            const { left, top, idx } = u.cursor;
            if (idx == null || left == null || left < 0 || top == null) { tip.classList.add('hidden'); return; }
            const j = (marks ?? []).findIndex((m) => Math.abs(u.valToPos(xOf(m.at), 'x') - left) <= 6);
            setTip(j >= 0 && markTips?.[j] ? [markTips[j]!] : tips[idx] ?? []);
            tip.classList.remove('hidden');
            const W = u.over.clientWidth;
            tip.style.maxWidth = `${W}px`;
            const w = tip.offsetWidth;
            const x = left > W / 2 ? left - w - 12 : left + 12;
            tip.style.left = `${Math.min(Math.max(x, 0), W - w)}px`;
            tip.style.top = `${Math.max(top - tip.offsetHeight - 8, 0)}px`;
          }],
          drawClear: [(u) => {
            u.ctx.fillStyle = 'rgba(0,0,0,0.07)';
            grey?.forEach((g, i) => {
              if (!g) return;
              const [a, b] = dayBox(i, dates).map((v) => u.valToPos(v, 'x', true)) as [number, number];
              u.ctx.fillRect(a, u.bbox.top, b - a, u.bbox.height);
            });
            const [lo, hi] = xRange(dates);
            for (const m of marks ?? []) {
              const t = xOf(m.at);
              if (t < lo || t > hi) continue;
              const px = u.valToPos(t, 'x', true);
              u.ctx.strokeStyle = m.color; u.ctx.lineWidth = 2; u.ctx.beginPath(); u.ctx.moveTo(px, u.bbox.top); u.ctx.lineTo(px, u.bbox.top + u.bbox.height); u.ctx.stroke();
            }
          }],
          draw: [(u) => {
            if (!reference) return;
            const py = u.valToPos(reference.value, 'y', true);
            const { ctx } = u;
            ctx.save();
            ctx.strokeStyle = '#5f6368'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
            ctx.beginPath(); ctx.moveTo(u.bbox.left, py); ctx.lineTo(u.bbox.left + u.bbox.width, py); ctx.stroke();
            ctx.setLineDash([]); ctx.fillStyle = '#5f6368'; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
            ctx.fillText(reference.label, u.bbox.left + u.bbox.width - 4, py - 3);
            ctx.restore();
          }],
        },
      },
      data,
      el.current!,
    );
    let lastW = el.current!.clientWidth;
    const ro = new ResizeObserver(() => {
      const w = el.current!.clientWidth;
      if (w === 0 || w === lastW) return;
      lastW = w;
      plot.setSize({ width: w, height });
    });
    ro.observe(el.current!);
    return () => { ro.disconnect(); plot.destroy(); };
  }, [dates, unit, lines, band, grey, marks, tips, markTips, reference, yRange, height]);
  return <div ref={el} className="w-full" />;
}
