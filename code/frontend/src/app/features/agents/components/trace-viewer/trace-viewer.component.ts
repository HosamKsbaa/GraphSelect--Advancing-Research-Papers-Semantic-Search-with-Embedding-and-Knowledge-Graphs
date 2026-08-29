import { Component, OnDestroy, OnInit, OnChanges, SimpleChanges, signal, computed, inject, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription, interval } from 'rxjs';
import { AgentService, LiveAgentTrace, ToolCallTrace } from '../../../../core/agent.service';
import { ToastService } from '../../../../core/toast.service';

@Component({
  selector: 'app-trace-viewer',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './trace-viewer.component.html',
  styleUrl: './trace-viewer.component.scss',
})
export class TraceViewerComponent implements OnInit, OnChanges, OnDestroy {
  private agentService = inject(AgentService);
  private toast = inject(ToastService);

  @Input() set initialAgentFilter(value: string | undefined) {
    if (value) {
      this.selectedAgent.set(value);
    }
  }
  @Input() availableAgents: string[] = [];

  // State
  traces = signal<LiveAgentTrace[]>([]);
  loading = signal<boolean>(false);
  autoRefreshEnabled = signal<boolean>(false);
  refreshIntervalSeconds = signal<number>(5);

  // Filters
  selectedAgent = signal<string>('all');
  selectedStatus = signal<string>('all');
  searchQuery = signal<string>('');
  projectIdFilter = signal<string>('');
  traceLimit = signal<number>(100);

  // Expanded sections state map: [traceId_sectionName]: boolean
  expandedSections = signal<Record<string, boolean>>({});
  copiedState = signal<string | null>(null);

  // Known agents list for dropdown filter
  knownAgents: string[] = [
    'ProjectAgent',
    'ResearchAgent',
    'ALRSAgent',
    'GapFinderAgent',
    'EvidenceSynthesizerAgent',
    'PlannerAgent',
    'DraftingAgent',
    'ReviewerAgent',
    'DebuggerAgent',
  ];

  private pollSubscription?: Subscription;

  // Filtered traces computation
  filteredTraces = computed(() => {
    const list = this.traces();
    const agent = this.selectedAgent();
    const status = this.selectedStatus();
    const query = this.searchQuery().trim().toLowerCase();
    const proj = this.projectIdFilter().trim().toLowerCase();

    return list.filter((t) => {
      // Agent filter
      if (agent !== 'all' && t.agent_name.toLowerCase() !== agent.toLowerCase()) {
        return false;
      }
      // Status filter
      if (status !== 'all' && t.status.toLowerCase() !== status.toLowerCase()) {
        return false;
      }
      // Project ID filter
      if (proj && (!t.project_id || !t.project_id.toLowerCase().includes(proj))) {
        return false;
      }
      // Search query
      if (query) {
        const inSummary = t.action_summary?.toLowerCase().includes(query) || false;
        const inAgent = t.agent_name?.toLowerCase().includes(query) || false;
        const inPrompt = t.llm_prompt?.toLowerCase().includes(query) || false;
        const inResponse = t.llm_response?.toLowerCase().includes(query) || false;
        const inTools = t.tool_calls?.some(
          (tc) =>
            tc.name.toLowerCase().includes(query) ||
            JSON.stringify(tc.arguments).toLowerCase().includes(query) ||
            tc.result?.toLowerCase().includes(query)
        ) || false;

        if (!inSummary && !inAgent && !inPrompt && !inResponse && !inTools) {
          return false;
        }
      }
      return true;
    });
  });

  ngOnInit(): void {
    if (this.initialAgentFilter) {
      this.selectedAgent.set(this.initialAgentFilter);
    }
    this.fetchTraces();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['initialAgentFilter'] && this.initialAgentFilter) {
      this.selectedAgent.set(this.initialAgentFilter);
      this.fetchTraces();
    }
  }

  ngOnDestroy(): void {
    this.stopAutoRefresh();
  }

  fetchTraces(isBackground = false): void {
    if (!isBackground) {
      this.loading.set(true);
    }

    const filters = {
      agent_name: this.selectedAgent() !== 'all' ? this.selectedAgent() : undefined,
      project_id: this.projectIdFilter().trim() || undefined,
      limit: this.traceLimit(),
    };

    this.agentService.getTraces(filters).subscribe({
      next: (res) => {
        this.traces.set(res.traces || []);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        if (!isBackground) {
          this.toast.error(
            'Failed to Fetch Traces',
            err.error?.detail || err.message || 'Could not load execution traces from server.'
          );
        }
      },
    });
  }

  toggleAutoRefresh(): void {
    const newState = !this.autoRefreshEnabled();
    this.autoRefreshEnabled.set(newState);
    if (newState) {
      this.startAutoRefresh();
      this.toast.info('Live Polling Active', `Tracing feed refreshing every ${this.refreshIntervalSeconds()}s.`);
    } else {
      this.stopAutoRefresh();
      this.toast.info('Live Polling Paused', 'Traces will not auto-refresh.');
    }
  }

  private startAutoRefresh(): void {
    this.stopAutoRefresh();
    this.pollSubscription = interval(this.refreshIntervalSeconds() * 1000).subscribe(() => {
      this.fetchTraces(true);
    });
  }

  private stopAutoRefresh(): void {
    if (this.pollSubscription) {
      this.pollSubscription.unsubscribe();
      this.pollSubscription = undefined;
    }
  }

  isSectionExpanded(traceId: string, section: 'prompt' | 'response' | 'tools' | 'raw'): boolean {
    return !!this.expandedSections()[`${traceId}_${section}`];
  }

  toggleSection(traceId: string, section: 'prompt' | 'response' | 'tools' | 'raw'): void {
    const key = `${traceId}_${section}`;
    this.expandedSections.update((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }

  formatJson(obj: unknown): string {
    try {
      if (typeof obj === 'string') {
        return obj;
      }
      return JSON.stringify(obj, null, 2);
    } catch {
      return String(obj);
    }
  }

  formatLatency(ms?: number | null): string {
    if (ms === undefined || ms === null) return '—';
    if (ms < 1000) return `⚡ ${Math.round(ms)}ms`;
    return `⚡ ${(ms / 1000).toFixed(2)}s`;
  }

  formatTokens(tokens: number): string {
    return `${tokens.toLocaleString()} tokens`;
  }

  copyToClipboard(text: string, label: string): void {
    navigator.clipboard.writeText(text).then(() => {
      this.copiedState.set(label);
      setTimeout(() => {
        if (this.copiedState() === label) {
          this.copiedState.set(null);
        }
      }, 2000);
    });
  }

  copyFullTrace(trace: LiveAgentTrace): void {
    this.copyToClipboard(JSON.stringify(trace, null, 2), `trace_${trace.id}`);
  }

  copyPrompt(trace: LiveAgentTrace): void {
    this.copyToClipboard(trace.llm_prompt || '', `prompt_${trace.id}`);
  }

  copyResponse(trace: LiveAgentTrace): void {
    this.copyToClipboard(trace.llm_response || '', `response_${trace.id}`);
  }

  copyToolCall(toolCall: ToolCallTrace, traceId: string, index: number): void {
    this.copyToClipboard(JSON.stringify(toolCall, null, 2), `tool_${traceId}_${index}`);
  }
}
