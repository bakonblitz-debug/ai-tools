'use client';
import { useEffect, useRef } from 'react';
import uPlot from 'uplot';
import 'uplot/dist/uPlot.min.css';

export type SparkProps = {
  dates: string[];
  lines: { label: string; data: (number | null)[]; color: string }[];
  band?: { lo: (number | null)[]; hi: (number | null)[] };
  grey?: boolean[]; // low-n days, shaded
};


export default function Spark({ dates, lines, band, grey }: SparkProps) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const x = dates.map((d) => Date.parse(d) / 1000);
    const data: uPlot.AlignedData = [x, ...lines.map((l) => l.data), ...(band ? [band.lo, band.hi] : [])];
    const n = lines.length;
    const series: uPlot.Series[] = [
      {},
      ...lines.map((l) => ({ label: l.label, stroke: l.color, width: 2, spanGaps: false, points: { show: false } })),
      ...(band ? [{ label: 'p25', stroke: 'transparent', points: { show: false } }, { label: 'p75', stroke: 'transparent', points: { show: false } }] : []),
    ];
    const plot = new uPlot(
      {
        width: el.current!.clientWidth, height: 70, legend: { show: false }, cursor: { show: false },
        scales: { x: { time: true } },
        axes: [{ show: false }, { show: false }], padding: [4, 2, 4, 2],
        series,
        bands: band ? [{ series: [n + 2, n + 1], fill: 'rgba(21,101,192,0.15)' }] : [],
        hooks: {
          drawClear: [(u) => {
            if (!grey) return;
            const w = u.bbox.width / Math.max(dates.length - 1, 1);
            u.ctx.fillStyle = 'rgba(0,0,0,0.07)';
            grey.forEach((g, i) => g && u.ctx.fillRect(u.valToPos(x[i]!, 'x', true) - w / 2, u.bbox.top, w, u.bbox.height));
          }],
        },
      },
      data,
      el.current!,
    );
    return () => plot.destroy();
  }, [dates, lines, band, grey]);
  return <div ref={el} className="w-full" />;
}
