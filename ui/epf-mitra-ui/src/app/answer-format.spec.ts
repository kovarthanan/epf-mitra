import { formatAnswer } from './answer-format';
import { Source } from './epf-api';

const src = (rank: number): Source => ({
  rank, title: `Doc ${rank}`, date: '2025-04-03', division: 'wsu', page_start: 1, url: `https://x/${rank}.pdf`, ocr: false, cited: true,
});

describe('formatAnswer', () => {
  it('turns [n] into citations linked to the right source', () => {
    const [line] = formatAnswer('No upload needed [5].', [src(5)]);
    expect(line.segments[1]).toEqual({ kind: 'cite', n: 5, source: src(5) });
  });

  it('detects bullets, bold text and skips empty lines', () => {
    const lines = formatAnswer('Steps:\n\n- **Login** to the portal [1]', [src(1)]);
    expect(lines.length).toBe(2);
    expect(lines[1].bullet).toBe(true);
    expect(lines[1].segments[0]).toEqual({ kind: 'bold', text: 'Login' });
  });
});
