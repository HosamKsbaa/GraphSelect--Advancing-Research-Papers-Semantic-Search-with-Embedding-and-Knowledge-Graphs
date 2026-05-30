import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { ToastService, Toast } from './toast.service';

@Component({
  selector: 'alrs-toast-container',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <div class="toast-container">
      @for (toast of activeToasts; track toast.id) {
        <div class="toast toast-{{ toast.type }} animate-slide-in-right" [class.toast-exiting]="exitingIds.has(toast.id)">
          <div class="toast-icon">
            @if (toast.type === 'error') {
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
            } @else if (toast.type === 'warning') {
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
            } @else if (toast.type === 'success') {
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
            } @else {
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
            }
          </div>
          <div class="toast-content">
            <div class="toast-title">{{ toast.title }}</div>
            <div class="toast-message">{{ toast.message }}</div>
            @if (toast.action) {
              <a class="toast-action" [routerLink]="toast.action.routerLink" (click)="dismiss(toast.id)">
                {{ toast.action.label }} →
              </a>
            }
          </div>
          <button class="toast-close" (click)="dismiss(toast.id)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      }
    </div>
  `,
  styles: [`
    .toast-container {
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 10000;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: 420px;
      width: 100%;
      pointer-events: none;
    }

    .toast {
      display: flex;
      align-items: flex-start;
      gap: var(--space-3);
      padding: var(--space-4) var(--space-5);
      border-radius: var(--radius-lg);
      backdrop-filter: blur(20px) saturate(1.8);
      border: 1px solid rgba(255, 255, 255, 0.1);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(0, 0, 0, 0.1);
      pointer-events: all;
      transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
    }

    .toast-exiting {
      opacity: 0;
      transform: translateX(100px);
    }

    .toast-error {
      background: rgba(239, 68, 68, 0.12);
      border-color: rgba(239, 68, 68, 0.3);
    }
    .toast-error .toast-icon { color: #f87171; }

    .toast-warning {
      background: rgba(245, 158, 11, 0.12);
      border-color: rgba(245, 158, 11, 0.3);
    }
    .toast-warning .toast-icon { color: #fbbf24; }

    .toast-success {
      background: rgba(16, 185, 129, 0.12);
      border-color: rgba(16, 185, 129, 0.3);
    }
    .toast-success .toast-icon { color: #34d399; }

    .toast-info {
      background: rgba(59, 130, 246, 0.12);
      border-color: rgba(59, 130, 246, 0.3);
    }
    .toast-info .toast-icon { color: #60a5fa; }

    .toast-icon {
      flex-shrink: 0;
      margin-top: 2px;
    }

    .toast-content {
      flex: 1;
      min-width: 0;
    }

    .toast-title {
      font-size: var(--text-sm);
      font-weight: 600;
      color: var(--color-text-primary);
      line-height: 1.3;
    }

    .toast-message {
      font-size: var(--text-xs);
      color: var(--color-text-secondary);
      margin-top: 2px;
      line-height: 1.4;
    }

    .toast-action {
      display: inline-block;
      margin-top: var(--space-2);
      font-size: var(--text-xs);
      font-weight: 600;
      color: var(--color-accent-hover);
      text-decoration: none;
      cursor: pointer;
      transition: color var(--transition-fast);
    }
    .toast-action:hover {
      color: var(--color-accent);
      text-decoration: underline;
    }

    .toast-close {
      flex-shrink: 0;
      background: none;
      border: none;
      color: var(--color-text-muted);
      cursor: pointer;
      padding: 4px;
      border-radius: var(--radius-sm);
      transition: all var(--transition-fast);
    }
    .toast-close:hover {
      color: var(--color-text-primary);
      background: rgba(255, 255, 255, 0.1);
    }

    @keyframes slideInRight {
      from { opacity: 0; transform: translateX(100px); }
      to   { opacity: 1; transform: translateX(0); }
    }
    .animate-slide-in-right {
      animation: slideInRight 0.35s cubic-bezier(0.22, 1, 0.36, 1);
    }
  `],
})
export class ToastContainerComponent implements OnInit, OnDestroy {
  activeToasts: Toast[] = [];
  exitingIds = new Set<number>();
  private subs: Subscription[] = [];
  private timers = new Map<number, ReturnType<typeof setTimeout>>();

  constructor(private toastService: ToastService) {}

  ngOnInit(): void {
    this.subs.push(
      this.toastService.toasts$.subscribe((toast) => {
        this.activeToasts.push(toast);
        // Auto-dismiss
        const timer = setTimeout(() => this.dismiss(toast.id), toast.duration);
        this.timers.set(toast.id, timer);
      }),
      this.toastService.dismiss$.subscribe((id) => {
        this.dismiss(id);
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
    this.timers.forEach((t) => clearTimeout(t));
  }

  dismiss(id: number): void {
    if (this.exitingIds.has(id)) return;
    this.exitingIds.add(id);
    // Wait for exit animation
    setTimeout(() => {
      this.activeToasts = this.activeToasts.filter((t) => t.id !== id);
      this.exitingIds.delete(id);
      const timer = this.timers.get(id);
      if (timer) {
        clearTimeout(timer);
        this.timers.delete(id);
      }
    }, 300);
  }
}
