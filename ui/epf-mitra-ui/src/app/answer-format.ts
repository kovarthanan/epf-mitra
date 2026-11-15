import { Source } from './epf-api';

/** One piece of a line: plain text, bold text, or a citation like [3]. */
export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'bold'; text: string }
  | { kind: 'cite'; n: number; source?: Source };

export interface Line {
  bullet: boolean;
  segments: Segment[];
}

/**
 * Turns the LLM's plain-text answer into structured lines for the template.
 * No innerHTML: citations become real links, everything else stays text (XSS-safe).
 */
export function formatAnswer(answer: string, sources: Source[]): Line[] {
  const byRank = new Map(sources.map((s) => [s.rank, s]));
  return answer
    .split('\n')
    .map((raw) => raw.trim())
    .filter((raw) => raw.length > 0)
    .map((raw) => {
      const bullet = /^[-*•]\s+/.test(raw);
      const text = bullet ? raw.replace(/^[-*•]\s+/, '') : raw;
      return { bullet, segments: toSegments(text, byRank) };
    });
}

function toSegments(text: string, byRank: Map<number, Source>): Segment[] {
  const out: Segment[] = [];
  // **bold** or [n]
  const re = /\*\*(.+?)\*\*|\[(\d+)\]/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push({ kind: 'text', text: text.slice(last, m.index) });
    if (m[1] !== undefined) out.push({ kind: 'bold', text: m[1] });
    else {
      const n = Number(m[2]);
      out.push({ kind: 'cite', n, source: byRank.get(n) });
    }
    last = m.index! + m[0].length;
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) });
  return out;
}
