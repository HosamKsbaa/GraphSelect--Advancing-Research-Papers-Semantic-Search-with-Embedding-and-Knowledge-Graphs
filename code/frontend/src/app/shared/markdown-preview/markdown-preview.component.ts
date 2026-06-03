import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { marked } from 'marked';

@Component({
  selector: 'app-markdown-preview',
  standalone: true,
  template: `
    <div class="markdown-body" [innerHTML]="html"></div>
  `,
  styles: [`
    :host ::ng-deep .markdown-body {
      color: var(--color-text-primary);
      font-size: var(--text-sm);
      line-height: 1.6;
    }
    :host ::ng-deep .markdown-body h1, 
    :host ::ng-deep .markdown-body h2, 
    :host ::ng-deep .markdown-body h3, 
    :host ::ng-deep .markdown-body h4 {
      color: var(--color-text-primary);
      margin-top: var(--space-6);
      margin-bottom: var(--space-3);
      font-weight: 600;
    }
    :host ::ng-deep .markdown-body h1 { font-size: var(--text-2xl); }
    :host ::ng-deep .markdown-body h2 { font-size: var(--text-xl); }
    :host ::ng-deep .markdown-body h3 { font-size: var(--text-lg); }
    :host ::ng-deep .markdown-body p { margin-bottom: var(--space-4); }
    :host ::ng-deep .markdown-body a { color: var(--color-accent); text-decoration: underline; }
    :host ::ng-deep .markdown-body ul, 
    :host ::ng-deep .markdown-body ol {
      margin-left: var(--space-6);
      margin-bottom: var(--space-4);
    }
    :host ::ng-deep .markdown-body li { margin-bottom: var(--space-1); }
    :host ::ng-deep .markdown-body code {
      font-family: var(--font-mono);
      background: var(--color-bg-input);
      padding: 0.2em 0.4em;
      border-radius: var(--radius-sm);
      font-size: 0.9em;
    }
    :host ::ng-deep .markdown-body pre {
      background: var(--color-bg-secondary);
      padding: var(--space-4);
      border-radius: var(--radius-md);
      overflow-x: auto;
      margin-bottom: var(--space-4);
      border: 1px solid var(--color-border);
    }
    :host ::ng-deep .markdown-body pre code {
      background: transparent;
      padding: 0;
    }
    :host ::ng-deep .markdown-body blockquote {
      border-left: 4px solid var(--color-accent);
      padding-left: var(--space-4);
      color: var(--color-text-secondary);
      margin-bottom: var(--space-4);
      background: var(--color-bg-hover);
      padding-top: var(--space-2);
      padding-bottom: var(--space-2);
      border-radius: 0 var(--radius-md) var(--radius-md) 0;
    }
  `]
})
export class MarkdownPreviewComponent implements OnChanges {
  @Input() markdown = '';
  html = '';

  async ngOnChanges(changes: SimpleChanges) {
    if (changes['markdown']) {
      if (!this.markdown) {
        this.html = '';
        return;
      }
      try {
        // Parse markdown to HTML. 
        // We bind directly to [innerHTML], which relies on Angular's DomSanitizer 
        // to strip unsafe tags (like <script>).
        this.html = await marked.parse(this.markdown);
      } catch (e) {
        console.error('Error parsing markdown', e);
        this.html = 'Error rendering markdown.';
      }
    }
  }
}
