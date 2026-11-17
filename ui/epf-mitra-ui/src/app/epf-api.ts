import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface Source {
  rank: number;
  title: string;
  date: string | null;
  division: string | null;
  page_start: number;
  url: string;
  ocr: boolean;
  cited: boolean;
}

export interface AskResponse {
  question: string;
  answer: string;
  sources: Source[];
  cost_inr: number;
  latency_s: { retrieve: number; total: number };
  questions_left: number;
  data_as_of: string | null;
}

/** Events of POST /api/ask/stream (Server-Sent Events). */
export type StreamEvent =
  | { type: 'sources'; sources: Omit<Source, 'cited'>[] }
  | { type: 'token'; text: string }
  | {
      type: 'done';
      answer: string;
      cited: number[];
      cost_inr: number;
      latency_s: { retrieve: number; total: number };
      questions_left: number;
      data_as_of: string | null;
    }
  | { type: 'error'; status: number; detail: string };

export interface Meta {
  data_as_of: string | null;
  documents: number;
  daily_limit: number;
  questions_left: number;
}

/** Thin wrapper over the FastAPI backend (/api is proxied to :8000 in dev, routed by Traefik in prod). */
@Injectable({ providedIn: 'root' })
export class EpfApi {
  private http = inject(HttpClient);

  meta(): Observable<Meta> {
    return this.http.get<Meta>('/api/meta');
  }

  ask(question: string): Observable<AskResponse> {
    return this.http.post<AskResponse>('/api/ask', { question });
  }

  /**
   * Streams the answer token by token. Uses fetch + ReadableStream because SSE over POST
   * is not possible with EventSource. Unsubscribing aborts the request.
   */
  askStream(question: string): Observable<StreamEvent> {
    return new Observable<StreamEvent>((sub) => {
      const ctrl = new AbortController();
      (async () => {
        const res = await fetch('/api/ask/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) {
          const body = await res.json().catch(() => ({}));
          sub.next({ type: 'error', status: res.status, detail: body?.detail ?? '' });
          sub.complete();
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let sep: number;
          while ((sep = buffer.indexOf('\n\n')) >= 0) {
            const evt = parseSse(buffer.slice(0, sep));
            buffer = buffer.slice(sep + 2);
            if (evt) sub.next(evt);
          }
        }
        sub.complete();
      })().catch((err) => {
        if (err?.name !== 'AbortError') sub.next({ type: 'error', status: 0, detail: '' });
        sub.complete();
      });
      return () => ctrl.abort();
    });
  }
}

/** "event: token\ndata: {...}" -> typed event */
export function parseSse(block: string): StreamEvent | null {
  let event = 'message';
  const data: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).trim());
  }
  if (!data.length) return null;
  const payload = JSON.parse(data.join('\n'));
  switch (event) {
    case 'sources':
      return { type: 'sources', sources: payload };
    case 'token':
      return { type: 'token', text: payload.text };
    case 'done':
      return { type: 'done', ...payload };
    case 'error':
      return { type: 'error', status: 500, detail: payload.detail };
    default:
      return null;
  }
}
