import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { AskResponse, EpfApi, Meta, Source } from './epf-api';
import { Line, formatAnswer } from './answer-format';

interface Message {
  id: number;
  role: 'user' | 'bot' | 'error';
  text: string;
  streaming?: boolean;
  response?: AskResponse;
  lines?: Line[];
  showAllSources?: boolean;
}

@Component({
  selector: 'app-root',
  imports: [DatePipe],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private api = inject(EpfApi);
  private scroller = viewChild<ElementRef<HTMLElement>>('scroller');

  protected readonly examples = [
    'Do I need to upload a cancelled cheque for a PF claim?',
    'What is the current EPF interest rate?',
    'Can I withdraw PF for my daughter’s marriage?',
    'How do I link Aadhaar with my UAN?',
  ];

  protected readonly meta = signal<Meta | null>(null);
  protected readonly messages = signal<Message[]>([]);
  protected readonly draft = signal('');
  protected readonly loading = signal(false);
  /** true until the first token arrives: shows "Searching N documents…" instead of an empty bubble */
  protected readonly searching = signal(false);
  private nextId = 0;

  protected readonly questionsLeft = computed(() => this.meta()?.questions_left ?? null);
  protected readonly limitReached = computed(() => this.questionsLeft() === 0);
  protected readonly canSend = computed(
    () => this.draft().trim().length >= 5 && !this.loading() && !this.limitReached(),
  );

  constructor() {
    this.api.meta().subscribe({
      next: (m) => this.meta.set(m),
      error: () => {
        this.push({ role: 'error', text: 'The EPF Mitra server is not reachable right now.' });
      },
    });
  }

  protected useExample(q: string): void {
    this.draft.set(q);
    this.send();
  }

  protected onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this.send();
    }
  }

  protected send(): void {
    if (!this.canSend()) return;
    const question = this.draft().trim();
    this.draft.set('');
    this.push({ role: 'user', text: question });
    this.loading.set(true);
    this.searching.set(true);

    let botId: number | null = null;
    let sources: Source[] = [];
    let text = '';

    this.api.askStream(question).subscribe({
      next: (evt) => {
        switch (evt.type) {
          case 'sources':
            sources = evt.sources.map((s) => ({ ...s, cited: false }));
            break;
          case 'token':
            text += evt.text;
            if (botId === null) {
              this.searching.set(false);
              botId = this.push({ role: 'bot', text, streaming: true, lines: formatAnswer(text, sources) });
            } else {
              this.patch(botId, { text, lines: formatAnswer(text, sources) });
            }
            break;
          case 'done': {
            const final = sources.map((s) => ({ ...s, cited: evt.cited.includes(s.rank) }));
            const response: AskResponse = {
              question, answer: evt.answer, sources: final, cost_inr: evt.cost_inr,
              latency_s: evt.latency_s, questions_left: evt.questions_left, data_as_of: evt.data_as_of,
            };
            const patch = { text: evt.answer, lines: formatAnswer(evt.answer, final), response, streaming: false };
            if (botId === null) botId = this.push({ role: 'bot', ...patch });
            else this.patch(botId, patch);
            this.meta.update((m) => (m ? { ...m, questions_left: evt.questions_left } : m));
            break;
          }
          case 'error': {
            if (botId !== null) this.patch(botId, { streaming: false });
            this.push({ role: 'error', text: this.errorText(evt.status, evt.detail) });
            if (evt.status === 429) this.meta.update((m) => (m ? { ...m, questions_left: 0 } : m));
            break;
          }
        }
      },
      complete: () => {
        this.loading.set(false);
        this.searching.set(false);
      },
    });
  }

  private errorText(status: number, detail: string): string {
    if (status === 429) return detail || 'Daily question limit reached. Please come back tomorrow.';
    if (status === 422) return 'Please ask a question between 5 and 500 characters.';
    if (status === 0) return 'Connection lost. Please check your internet and try again.';
    return detail || 'Something went wrong while answering. Please try again.';
  }

  protected toggleSources(msg: Message): void {
    this.patch(msg.id, { showAllSources: !msg.showAllSources });
  }

  protected visibleSources(msg: Message) {
    const all = msg.response?.sources ?? [];
    return msg.showAllSources ? all : all.filter((s) => s.cited);
  }

  private push(m: Omit<Message, 'id'>): number {
    const id = this.nextId++;
    this.messages.update((list) => [...list, { ...m, id }]);
    this.scrollToEnd();
    return id;
  }

  private patch(id: number, changes: Partial<Message>): void {
    this.messages.update((list) => list.map((m) => (m.id === id ? { ...m, ...changes } : m)));
    this.scrollToEnd();
  }

  private scrollToEnd(): void {
    queueMicrotask(() => {
      const el = this.scroller()?.nativeElement;
      el?.scrollTo({ top: el.scrollHeight });
    });
  }
}
