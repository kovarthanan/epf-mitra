import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
  });

  it('shows the brand and data-as-of chip from /api/meta', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/meta').flush({ data_as_of: '2025-12-17', documents: 680, daily_limit: 10, questions_left: 10 });
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('h1')?.textContent).toContain('EPF Mitra');
    expect(el.textContent).toContain('Documents up to 17 Dec 2025');
    expect(el.textContent).toContain('10/10 questions left today');
  });
});
