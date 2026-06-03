import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, AppLog, ApiLog, AgentTrace, Project } from '../../core/api.service';

interface DisplayAppLog extends AppLog {
  formattedExtra?: string;
  badgeClass?: string;
}

interface DisplayApiLog extends ApiLog {
  statusClass?: string;
  formatted_request_body?: string;
  formatted_response_body?: string;
}

@Component({
  selector: 'alrs-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './logs.page.html',
  styleUrl: './logs.page.scss',
})
export class LogsPage implements OnInit {
  activeTab: 'app' | 'api' | 'agent' = 'app';
  appLogs: DisplayAppLog[] = [];
  apiLogs: DisplayApiLog[] = [];
  agentTraces: AgentTrace[] = [];
  projects: Project[] = [];
  loading = false;
  error = '';

  // Filter params
  levelFilter = '';
  serviceFilter = '';
  
  // Agent Trace Filters
  projectIdFilter = '';
  agentNameFilter = '';
  sinceFilter = '';
  endTimeFilter = '';

  limit = 100;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.loadProjects();
    this.loadLogs();
  }

  setTab(tab: 'app' | 'api' | 'agent'): void {
    if (this.activeTab !== tab) {
      this.activeTab = tab;
      this.error = '';
      this.loadLogs();
    }
  }

  loadProjects(): void {
    this.api.listProjects().subscribe({
      next: (res) => {
        this.projects = res;
      },
      error: (err) => {
        console.error('Failed to load projects for dropdown', err);
      }
    });
  }

  loadLogs(): void {
    this.loading = true;
    this.error = '';

    if (this.activeTab === 'app') {
      const level = this.levelFilter || undefined;
      this.api.getAppLogs(level, undefined, undefined, this.limit).subscribe({
        next: (data) => {
          this.appLogs = data.map(log => ({
            ...log,
            formattedExtra: log.extra ? JSON.stringify(log.extra, null, 2) : '',
            badgeClass: this.getBadgeClass(log.level)
          }));
          this.loading = false;
        },
        error: (err) => {
          this.error = err.error?.detail || 'Failed to retrieve application logs.';
          this.loading = false;
        },
      });
    } else if (this.activeTab === 'api') {
      const service = this.serviceFilter || undefined;
      this.api.getApiLogs(service, undefined, this.limit).subscribe({
        next: (data) => {
          this.apiLogs = data.map(api => ({
            ...api,
            statusClass: this.getApiStatusClass(api.status_code),
            formatted_request_body: this.formatJsonString(api.request_body),
            formatted_response_body: this.formatJsonString(api.response_body)
          }));
          this.loading = false;
        },
        error: (err) => {
          this.error = err.error?.detail || 'Failed to retrieve API crawl logs.';
          this.loading = false;
        },
      });
    } else if (this.activeTab === 'agent') {
      const pId = this.projectIdFilter || undefined;
      const agent = this.agentNameFilter || undefined;
      const since = this.sinceFilter || undefined;
      const end = this.endTimeFilter || undefined;
      
      this.api.getAgentTraces(pId, agent, since, end, this.limit).subscribe({
        next: (res) => {
          this.agentTraces = res.traces;
          this.loading = false;
        },
        error: (err) => {
          this.error = err.error?.detail || 'Failed to retrieve agent traces.';
          this.loading = false;
        }
      });
    }
  }

  getBadgeClass(level: string | null | undefined): string {
    if (!level) return 'badge-accent';
    const lvl = level.toUpperCase();
    if (lvl === 'ERROR' || lvl === 'CRITICAL') return 'badge-error';
    if (lvl === 'WARNING' || lvl === 'WARN') return 'badge-warning';
    if (lvl === 'INFO') return 'badge-info';
    if (lvl === 'DEBUG') return 'badge-debug';
    return 'badge-accent';
  }

  getApiStatusClass(code: number | null): string {
    if (!code) return 'badge-accent';
    if (code >= 200 && code < 300) return 'badge-success';
    if (code >= 300 && code < 400) return 'badge-info';
    if (code >= 400 && code < 500) return 'badge-warning';
    return 'badge-error';
  }

  formatJsonString(str: any): string {
    if (!str) return '';
    if (typeof str === 'object') {
      return JSON.stringify(str, null, 2);
    }
    try {
      const parsed = JSON.parse(str);
      return JSON.stringify(parsed, null, 2);
    } catch (e) {
      return str;
    }
  }

  copiedId: string | number | null = null;
  copiedType: 'app' | 'api' | 'api-req' | 'api-res' | 'trace-prompt' | 'trace-res' | 'trace-args' = 'app';

  copyToClipboard(text: string, logId: string | number, type: 'app' | 'api' | 'api-req' | 'api-res' | 'trace-prompt' | 'trace-res' | 'trace-args', event: Event): void {
    event.stopPropagation();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        this.setCopiedState(logId, type);
      }).catch(err => {
        console.error('Failed to copy text using Clipboard API:', err);
        this.fallbackCopy(text, logId, type);
      });
    } else {
      this.fallbackCopy(text, logId, type);
    }
  }

  private setCopiedState(logId: string | number, type: 'app' | 'api' | 'api-req' | 'api-res' | 'trace-prompt' | 'trace-res' | 'trace-args'): void {
    this.copiedId = logId;
    this.copiedType = type;
    setTimeout(() => {
      if (this.copiedId === logId && this.copiedType === type) {
        this.copiedId = null;
      }
    }, 2000);
  }

  private fallbackCopy(text: string, logId: string | number, type: 'app' | 'api' | 'api-req' | 'api-res' | 'trace-prompt' | 'trace-res' | 'trace-args'): void {
    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.top = '0';
      textArea.style.left = '0';
      textArea.style.position = 'fixed';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);
      if (successful) {
        this.setCopiedState(logId, type);
      } else {
        console.error('Fallback copy command was unsuccessful');
      }
    } catch (err) {
      console.error('Fallback copy failed:', err);
    }
  }
}
