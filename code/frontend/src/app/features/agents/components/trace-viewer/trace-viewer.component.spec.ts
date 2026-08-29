import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { TraceViewerComponent } from './trace-viewer.component';
import { AgentService, AgentTraceListResponse } from '../../../../core/agent.service';
import { ToastService } from '../../../../core/toast.service';

describe('TraceViewerComponent', () => {
  let component: TraceViewerComponent;
  let fixture: ComponentFixture<TraceViewerComponent>;
  let agentServiceMock: any;
  let toastMock: any;

  const mockTraceResponse: AgentTraceListResponse = {
    traces: [
      {
        id: 'trace-1',
        timestamp: '2026-08-29T12:00:00Z',
        agent_name: 'ProjectAgent',
        action_summary: 'Delegated research scoping to ResearchAgent',
        llm_prompt: 'System prompt instructions...',
        llm_response: '{"task": "scope_rqs"}',
        tool_calls: [],
        token_count: 850,
        latency_ms: 240,
        status: 'success',
        decision_outcome: 'Proceed to citation graph exploration',
      },
      {
        id: 'trace-2',
        timestamp: '2026-08-29T12:05:00Z',
        agent_name: 'ALRSAgent',
        action_summary: '1-Hop traversal failed due to network timeout',
        tool_calls: [],
        token_count: 120,
        latency_ms: 5000,
        status: 'error',
      },
    ],
    total: 2,
  };

  beforeEach(async () => {
    agentServiceMock = {
      getTraces: vi.fn().mockReturnValue(of(mockTraceResponse)),
    };
    toastMock = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [TraceViewerComponent],
      providers: [
        { provide: AgentService, useValue: agentServiceMock },
        { provide: ToastService, useValue: toastMock },
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(TraceViewerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create the component and load traces', () => {
    expect(component).toBeTruthy();
    expect(component.traces().length).toBe(2);
    expect(component.filteredTraces().length).toBe(2);
  });

  it('should filter traces by agent name', () => {
    component.selectedAgent.set('ALRSAgent');
    fixture.detectChanges();

    const filtered = component.filteredTraces();
    expect(filtered.length).toBe(1);
    expect(filtered[0].agent_name).toBe('ALRSAgent');
  });

  it('should filter traces by status', () => {
    component.selectedStatus.set('error');
    fixture.detectChanges();

    const filtered = component.filteredTraces();
    expect(filtered.length).toBe(1);
    expect(filtered[0].status).toBe('error');
  });

  it('should filter traces by search query in summary, prompt, or response', () => {
    component.searchQuery.set('network timeout');
    fixture.detectChanges();

    const filtered = component.filteredTraces();
    expect(filtered.length).toBe(1);
    expect(filtered[0].id).toBe('trace-2');
  });

  it('should format latency correctly', () => {
    expect(component.formatLatency(240)).toBe('⚡ 240ms');
    expect(component.formatLatency(1500)).toBe('⚡ 1.50s');
    expect(component.formatLatency(null)).toBe('—');
  });
});
