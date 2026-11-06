/** ⓘ beside a title: explanation, formula, how to read it and the source. Pure CSS, opens on hover or keyboard focus. */
export default function Info({ title, explanation, reading, source, formula }: { title: string; explanation: string; reading: string; source: string; formula: string }) {
  return (
    <span className="group ml-1 inline-block font-normal">
      <button type="button" aria-label={`About ${title}`} className="cursor-help text-on-surface-variant">ⓘ</button>
      <span className="absolute left-0 top-full z-10 hidden w-72 max-w-full flex-col gap-1 rounded-lg bg-surface p-3 text-xs text-on-surface shadow-e2 group-focus-within:flex group-hover:flex">
        <span>{explanation}</span>
        {/* static strings from src/formulas.ts only */}
        <span className="overflow-x-auto" style={{ fontFamily: 'math' }} dangerouslySetInnerHTML={{ __html: formula }} />
        <span>Reading: {reading}</span>
        <span>Source: {source}</span>
      </span>
    </span>
  );
}
