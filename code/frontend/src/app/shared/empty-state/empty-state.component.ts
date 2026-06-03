import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { RouterModule } from '@angular/router';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [RouterModule],
  template: `
    <div class="empty-state-container card">
      @if (safeIcon) {
        <div class="empty-icon" [innerHTML]="safeIcon"></div>
      }
      <h3 class="empty-heading">{{ heading }}</h3>
      <p class="empty-description text-secondary">{{ description }}</p>
      @if (ctaText && ctaLink) {
        <a class="btn btn-primary cta-btn" [routerLink]="ctaLink">{{ ctaText }}</a>
      } @else if (ctaText) {
        <button class="btn btn-primary cta-btn" (click)="onCtaClick()">{{ ctaText }}</button>
      }
    </div>
  `,
  styles: [`
    .empty-state-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: var(--space-10) var(--space-6);
      gap: var(--space-4);
      background: transparent;
      border: 1px dashed var(--color-border);
    }
    .empty-icon {
      width: 48px;
      height: 48px;
      color: var(--color-text-muted);
      margin-bottom: var(--space-2);
    }
    .empty-icon ::ng-deep svg {
      width: 100%;
      height: 100%;
      fill: currentColor;
    }
    .empty-heading {
      font-size: var(--text-lg);
      font-weight: 600;
      color: var(--color-text-primary);
    }
    .empty-description {
      font-size: var(--text-sm);
      max-width: 400px;
    }
    .cta-btn {
      margin-top: var(--space-2);
    }
  `]
})
export class EmptyStateComponent implements OnChanges {
  @Input() iconSvg?: string;
  @Input() heading = 'No data available';
  @Input() description = '';
  @Input() ctaText?: string;
  @Input() ctaLink?: string | any[];
  @Input() ctaAction?: () => void;

  safeIcon?: SafeHtml;

  constructor(private sanitizer: DomSanitizer) {}

  ngOnChanges(changes: SimpleChanges) {
    if (changes['iconSvg'] && this.iconSvg) {
      this.safeIcon = this.sanitizer.bypassSecurityTrustHtml(this.iconSvg);
    }
  }

  onCtaClick() {
    if (this.ctaAction) {
      this.ctaAction();
    }
  }
}
