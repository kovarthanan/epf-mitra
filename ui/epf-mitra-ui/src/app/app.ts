import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { AskResponse, EpfApi, Meta } from './epf-api';
import { Line, formatAnswer } from './answer-format';

interface Message {
  role: 'user' | 'bot' | 'error';
  text: string;
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

  protected readonly questionsLeft = computed(() => this.meta()?.questions_left ?? null);
  protected readonly limitReached = computed(() => this.questionsLeft() === 0);
  protected readonly canSend = computed(
    () => this.draft().trim().length >= 5 && !this.loading() && !this.limitReached(),
  );

  constructor() {
    this.api.meta().subscribe({
      next: (m) => this.meta.set(m),
      error: () => this.push({ role: 'error', text: 'The EPF Mitra server is not reachable right now.' }),
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

    this.api.ask(question).subscribe({
      next: (r) => {
        this.push({ role: 'bot', text: r.answer, response: r, lines: formatAnswer(r.answer, r.sources) });
        this.meta.update((m) => (m ? { ...m, questions_left: r.questions_left } : m));
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        const text =
          err.status === 429
            ? err.error?.detail ?? 'Daily question limit reached. Please come back tomorrow.'
            : err.status === 422
              ? 'Please ask a question between 5 and 500 characters.'
              : 'Something went wrong while answering. Please try again.';
        if (err.status === 429) this.meta.update((m) => (m ? { ...m, questions_left: 0 } : m));
        this.push({ role: 'error', text });
        this.loading.set(false);
      },
    });
  }

  protected toggleSources(msg: Message): void {
    this.messages.update((list) => list.map((m) => (m === msg ? { ...m, showAllSources: !m.showAllSources } : m)));
  }

  protected visibleSources(msg: Message) {
    const all = msg.response?.sources ?? [];
    return msg.showAllSources ? all : all.filter((s) => s.cited);
  }

  private push(m: Message): void {
    this.messages.update((list) => [...list, m]);
    queueMicrotask(() => {
      const el = this.scroller()?.nativeElement;
      el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });
  }
}
