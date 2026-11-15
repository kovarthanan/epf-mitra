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
}
