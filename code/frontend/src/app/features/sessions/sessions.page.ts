import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService, Session } from '../../core/api.service';

@Component({
  selector: 'alrs-sessions',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './sessions.page.html',
  styleUrl: './sessions.page.scss',
})
export class SessionsPage implements OnInit {
  sessions: Session[] = [];
  loading = true;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.loadSessions();
  }

  loadSessions(): void {
    this.loading = true;
    this.api.listSessions().subscribe({
      next: (data) => {
        this.sessions = data.sessions;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
      },
    });
  }

  deleteSession(sessionId: string): void {
    this.api.deleteSession(sessionId).subscribe({
      next: () => this.loadSessions(),
    });
  }

  getStatusBadge(status: string): string {
    const map: Record<string, string> = {
      created: 'badge-info', running: 'badge-warning',
      paused: 'badge-accent', completed: 'badge-success', failed: 'badge-error',
    };
    return map[status] || 'badge-info';
  }
}
