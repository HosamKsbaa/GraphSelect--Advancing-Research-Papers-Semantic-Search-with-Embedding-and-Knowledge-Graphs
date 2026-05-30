import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService, HealthResponse, Session, SessionList } from '../../core/api.service';

@Component({
  selector: 'alrs-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './dashboard.page.html',
  styleUrl: './dashboard.page.scss',
})
export class DashboardPage implements OnInit {
  health: HealthResponse | null = null;
  version = '';
  sessions: Session[] = [];
  loading = true;
  error = '';

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.loadDashboard();
  }

  loadDashboard(): void {
    this.loading = true;
    this.error = '';

    this.api.getHealth().subscribe({
      next: (h) => (this.health = h),
      error: () => (this.health = { status: 'offline', neo4j: 'disconnected', mysql: 'disconnected' }),
    });

    this.api.getVersion().subscribe({
      next: (v) => (this.version = v.version),
      error: () => (this.version = 'unknown'),
    });

    this.api.listSessions().subscribe({
      next: (data) => {
        this.sessions = data.sessions.slice(0, 5);
        this.loading = false;
      },
      error: (err) => {
        this.error = 'Cannot connect to backend. Is the API running on localhost:8000?';
        this.loading = false;
      },
    });
  }

  getStatusBadge(status: string): string {
    const map: Record<string, string> = {
      healthy: 'badge-success',
      degraded: 'badge-warning',
      offline: 'badge-error',
      connected: 'badge-success',
      disconnected: 'badge-error',
    };
    return map[status] || 'badge-info';
  }

  getSessionStatusBadge(status: string): string {
    const map: Record<string, string> = {
      created: 'badge-info',
      running: 'badge-warning',
      paused: 'badge-accent',
      completed: 'badge-success',
      failed: 'badge-error',
    };
    return map[status] || 'badge-info';
  }
}
