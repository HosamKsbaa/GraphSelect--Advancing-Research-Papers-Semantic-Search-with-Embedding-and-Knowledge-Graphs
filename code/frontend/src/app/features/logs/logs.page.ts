import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, AppLog, ApiLog } from '../../core/api.service';

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
  activeTab: 'app' | 'api' = 'app';
  appLogs: DisplayAppLog[] = [];
  apiLogs: DisplayApiLog[] = [];
  loading = false;
  error = '';

  // Filter params
  levelFilter = '';
  serviceFilter = '';
  limit = 100;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.loadLogs();
  }

  setTab(tab: 'app' | 'api'): void {
    if (this.activeTab !== tab) {
      this.activeTab = tab;
      this.error = '';
      this.loadLogs();
    }
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
    } else {
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

  private formatJsonString(str: string | null | undefined): string {
    if (!str) return '';
    try {
      const parsed = JSON.parse(str);
      return JSON.stringify(parsed, null, 2);
    } catch (e) {
      return str;
    }
  }

  copiedId: number | null = null;
  copiedType: 'app' | 'api' | 'api-req' | 'api-res' = 'app';

  copyToClipboard(text: string, logId: number, type: 'app' | 'api' | 'api-req' | 'api-res', event: Event): void {
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

  private setCopiedState(logId: number, type: 'app' | 'api' | 'api-req' | 'api-res'): void {
    this.copiedId = logId;
    this.copiedType = type;
    setTimeout(() => {
      if (this.copiedId === logId && this.copiedType === type) {
        this.copiedId = null;
      }
    }, 2000);
  }

  private fallbackCopy(text: string, logId: number, type: 'app' | 'api' | 'api-req' | 'api-res'): void {
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
