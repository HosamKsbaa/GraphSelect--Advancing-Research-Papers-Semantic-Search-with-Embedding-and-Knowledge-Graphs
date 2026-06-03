import { Component, Input, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-loading-indicator',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (show) {
      <div class="loading-overlay">
        <div class="card glass loading-card">
          <div class="spinner"></div>
          @if (message) {
            <div class="message">{{ message }}</div>
          }
        </div>
      </div>
    }
  `,
  styles: [`
    .loading-overlay {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 100;
      background: rgba(10, 14, 26, 0.4);
      backdrop-filter: blur(2px);
    }
    .loading-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-4);
      padding: var(--space-6) var(--space-8);
      animation: fadeIn var(--transition-base);
    }
    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid var(--color-border);
      border-top-color: var(--color-accent);
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    .message {
      color: var(--color-text-primary);
      font-weight: 500;
      font-size: var(--text-sm);
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  `]
})
export class LoadingIndicatorComponent implements OnInit, OnDestroy {
  @Input() message?: string;
  @Input() delay = 200;

  show = false;
  private timeoutId: any;

  ngOnInit() {
    this.timeoutId = setTimeout(() => {
      this.show = true;
    }, this.delay);
  }

  ngOnDestroy() {
    if (this.timeoutId) {
      clearTimeout(this.timeoutId);
    }
  }
}
