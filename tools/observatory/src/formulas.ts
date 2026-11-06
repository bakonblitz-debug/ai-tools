// MathML as plain strings (@types/react has no MathML intrinsics, so no JSX).
const i = (s: string) => (s.includes(' ') ? `<mtext>${s}</mtext>` : `<mi>${s}</mi>`);
const frac = (a: string, b: string) => `<mfrac><mrow>${a}</mrow><mrow>${b}</mrow></mfrac>`;
const sumOver = (what: string) => `<munder><mo>∑</mo><mrow>${i('d')}<mo>∈</mo>${i('week')}</mrow></munder>${what}`;
const m = (body: string) => `<math display="block"><mrow>${body}</mrow></math>`;
const inDay = (what: string) => `<munder><mo>∑</mo><mrow>${i('s')}<mo>∈</mo>${i('day')}</mrow></munder>${what}`;
const weekAvg = (what: string) => m(`${i('headline')}<mo>=</mo>${frac(sumOver(what), '<mn>7</mn>')}`);
const daily = (name: string, what: string) => m(`<msub>${i(name)}${i('d')}</msub><mo>=</mo>${what}`);
const sub = (a: string, b: string) => `<msub>${i(a)}${i(b)}</msub>`;

export const FORMULAS: Record<string, string> = {
  // sessions: count of main sessions started per day; headline = last 7 days / 7
  sessions: weekAvg(`<mo>#</mo>${i('main sessions started on d')}`),
  active: daily('hours', frac(inDay(i('active_s')), '<mn>3600</mn>')),
  // cost is summed from the recorded cost_usd, not recomputed as tokens x price
  models: m(`${i('tokens')}<mo>=</mo>${inDay(`<mo>(</mo>${i('in')}<mo>+</mo>${i('out')}<mo>+</mo>${i('cache_read')}<mo>+</mo>${i('cache_create')}<mo>)</mo>`)}<mtext> per model; cost = </mtext>${inDay(i('cost_usd'))}`),
  effort: m(`${i('share')}<mo>=</mo>${frac(sub('requests', 'level'), sub('requests', 'all'))}`),
  // the code divides by assistant messages, not requests
  toolErrors: daily('rate', `<mn>100</mn><mo>×</mo>${frac(inDay(i('tool_errors')), inDay(i('assistant_msgs')))}`),
  interruptions: daily('rate', frac(inDay(i('interruptions')), inDay(frac(i('active_s'), '<mn>3600</mn>')))),
  denials: daily('denials', inDay(i('denials'))),
  cache: m(`${i('ratio')}<mo>=</mo>${frac(i('cache_read'), `${i('cache_read')}<mo>+</mo>${i('cache_create')}<mo>+</mo>${i('input')}`)}`),
  coverage: m(`${i('coverage')}<mo>=</mo>${frac(i('OTel api_request'), i('transcript requests'))}`),
  toolDecisions: m(`${i('count')}<mo>=</mo>${sumOver(`<msub>${i('decisions')}${i('source')}</msub>`)}`),
  apiErrors: m(`${i('rate')}<mo>=</mo><mn>100</mn><mo>×</mo>${frac(i('errors and refusals'), i('requests'))}`),
  hooks: m(`${i('total')}<mo>=</mo>${sumOver(i('duration_ms'))}`),
  heatmap: m(`${i('cell')}<mo>=</mo><mo>#</mo><mo>{</mo>${i('sessions')}<mo>:</mo>${i('weekday')}<mo>,</mo>${i('hour')}<mo>}</mo>`),
  overlays: m(`${i('line')}<mo>=</mo>${i('commit time')}<mo>,</mo>${i('colored by tag')}`),
};

export const PANELS: Record<string, { title: string; explanation: string; reading: string; source: string }> = {
  coverage: {
    title: 'Telemetry coverage (OTel api_request / transcript requests)',
    explanation: 'Grey days have telemetry for under 90% of the transcript\'s requests: gaps mean missing telemetry (Mac asleep, receiver down), not zero activity.',
    reading: 'A value near 100% means telemetry saw nearly every request the transcripts recorded. Grey days are too incomplete to trust in the panels below.',
    source: 'otel.db: api_request events; sessions.tsv: assistant_msgs',
  },
  toolDecisions: {
    title: 'Tool decisions by source, per day',
    explanation: 'How each tool call was decided (allowed or refused, and by what), counted per day. Grey days have incomplete telemetry.',
    reading: 'Each colour is one decision source; the stack height is all tool decisions that day. Compare the mix, not just the height.',
    source: 'otel.db: tool_decision events',
  },
  apiErrors: {
    title: 'API errors and refusals per 100 requests, by model and effort',
    explanation: 'Totals over the window, including the grey days. Telemetry panels honour machine, model, effort and days; project and agent filters do not apply to them.',
    reading: 'Rows with few requests swing wildly; read the request count before the rate.',
    source: 'otel.db: api_request and api_error events',
  },
  hooks: {
    title: 'Hook time (top by total duration)',
    explanation: 'Per-run duration (ms) from hook_execution_complete; hook names are hashed by the receiver.',
    reading: 'The hooks at the top cost the most total time across the window; a high maximum with a low median means occasional stalls.',
    source: 'otel.db: hook_execution_complete events',
  },
  heatmap: {
    title: 'When sessions start (weekday x hour)',
    explanation: 'Main sessions in the current filters, in local time; darker means more starts.',
    reading: 'Each cell counts sessions that started in that weekday and hour. Dark cells are the habitual working hours.',
    source: 'sessions.tsv: started',
  },
  overlays: {
    title: 'Harness changes (vertical lines on the charts)',
    explanation: 'Commits to the harness repository, drawn as vertical lines on the charts so a change can be compared with what happened after it.',
    reading: 'A line marks when a commit landed. A metric moving after a line is a hint, not proof the commit caused it.',
    source: 'git log of the harness repository',
  },
};
