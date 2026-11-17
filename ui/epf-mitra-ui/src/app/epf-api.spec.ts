import { parseSse } from './epf-api';

describe('parseSse', () => {
  it('parses token, done and error events', () => {
    expect(parseSse('event: token\ndata: {"text": "Hello "}')).toEqual({ type: 'token', text: 'Hello ' });
    const done = parseSse('event: done\ndata: {"answer": "x", "cited": [1], "cost_inr": 0.02, "latency_s": {"retrieve": 1, "total": 2}, "questions_left": 9, "data_as_of": null}');
    expect(done?.type).toBe('done');
    expect(parseSse('event: error\ndata: {"detail": "boom"}')).toEqual({ type: 'error', status: 500, detail: 'boom' });
  });

  it('ignores blocks without data', () => {
    expect(parseSse(': keep-alive')).toBeNull();
  });
});
