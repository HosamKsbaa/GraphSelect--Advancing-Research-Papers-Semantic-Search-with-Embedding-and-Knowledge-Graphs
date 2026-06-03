import { Component, Input, Output, EventEmitter, ElementRef, ViewChild, AfterViewInit } from '@angular/core';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  template: `
    <div class="modal-backdrop" (click)="onCancel()">
      <div class="card glass modal-dialog" (click)="$event.stopPropagation()" role="dialog" aria-modal="true" aria-labelledby="dialogTitle">
        <h2 id="dialogTitle" class="modal-title">{{ title }}</h2>
        <p class="modal-message">{{ message }}</p>
        <div class="modal-actions">
          <button #cancelBtn class="btn btn-secondary" (click)="onCancel()" (keydown.shift.tab)="trapFocus($event, 'cancel')">Cancel</button>
          <button #confirmBtn class="btn btn-primary" (click)="onConfirm()" (keydown.tab)="trapFocus($event, 'confirm')">Confirm</button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .modal-backdrop {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.6);
      backdrop-filter: blur(4px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      animation: fadeIn var(--transition-fast);
    }
    .modal-dialog {
      width: 100%;
      max-width: 400px;
      padding: var(--space-6);
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      animation: slideInTop 0.2s ease-out;
    }
    .modal-title {
      font-size: var(--text-lg);
      font-weight: 600;
      color: var(--color-text-primary);
    }
    .modal-message {
      font-size: var(--text-sm);
      color: var(--color-text-secondary);
      line-height: 1.5;
    }
    .modal-actions {
      display: flex;
      justify-content: flex-end;
      gap: var(--space-3);
      margin-top: var(--space-2);
    }
    @keyframes slideInTop {
      from { opacity: 0; transform: translateY(-20px); }
      to { opacity: 1; transform: translateY(0); }
    }
  `]
})
export class ConfirmDialogComponent implements AfterViewInit {
  @Input() title = 'Confirm Action';
  @Input() message = 'Are you sure you want to proceed?';
  @Output() confirmed = new EventEmitter<void>();
  @Output() cancelled = new EventEmitter<void>();

  @ViewChild('cancelBtn') cancelBtn!: ElementRef;
  @ViewChild('confirmBtn') confirmBtn!: ElementRef;

  ngAfterViewInit() {
    // Focus the cancel button by default for safety
    setTimeout(() => this.cancelBtn.nativeElement.focus(), 0);
  }

  onConfirm() {
    this.confirmed.emit();
  }

  onCancel() {
    this.cancelled.emit();
  }

  trapFocus(e: Event, buttonType: 'cancel' | 'confirm') {
    const event = e as KeyboardEvent;
    if (buttonType === 'cancel' && event.shiftKey && event.key === 'Tab') {
      event.preventDefault();
      this.confirmBtn.nativeElement.focus();
    } else if (buttonType === 'confirm' && !event.shiftKey && event.key === 'Tab') {
      event.preventDefault();
      this.cancelBtn.nativeElement.focus();
    }
  }
}
