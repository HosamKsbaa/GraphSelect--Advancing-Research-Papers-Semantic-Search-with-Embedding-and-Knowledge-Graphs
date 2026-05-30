import { Component, Input, OnInit, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, GroupedResults, QuestionGroup, RankedPaper } from '../../../core/api.service';

@Component({
  selector: 'alrs-results',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './results.component.html',
  styleUrl: './results.component.scss',
})
export class ResultsComponent implements OnInit {
  @Input() sessionId: string = '';
  @Input() set initialResults(value: GroupedResults | null) {
    if (value) {
      this.results = value;
      this.similarityThreshold = value.similarity_threshold;
      this.similarityWeight = value.similarity_weight;
      this.pagerankWeight = value.pagerank_weight;
    }
  }

  @Output() reset = new EventEmitter<void>();

  results: GroupedResults | null = null;
  loading = false;
  reranking = false;
  error = '';

  // Sliders state
  similarityThreshold = 0.5;
  similarityWeight = 0.7;
  pagerankWeight = 0.3;

  // Active question tab index
  activeTabIndex = 0;

  // Track expanded paper drawers
  expandedPapers: Set<string> = new Set();

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    if (!this.results && this.sessionId) {
      this.loadResults();
    }
  }

  loadResults(): void {
    this.loading = true;
    this.error = '';

    this.api.getResults(this.sessionId, this.similarityWeight, this.pagerankWeight).subscribe({
      next: (data) => {
        this.results = data;
        this.similarityThreshold = data.similarity_threshold;
        this.similarityWeight = data.similarity_weight;
        this.pagerankWeight = data.pagerank_weight;
        this.loading = false;
        
        // Auto-select first tab that has papers, if any
        this.autoSelectActiveTab();
      },
      error: (err) => {
        this.error = err.error?.detail || 'Failed to retrieve literature review results.';
        this.loading = false;
      },
    });
  }

  triggerRerank(): void {
    if (!this.sessionId) return;
    this.reranking = true;
    this.error = '';

    this.api
      .rerank(
        this.sessionId,
        this.similarityThreshold,
        this.similarityWeight,
        this.pagerankWeight
      )
      .subscribe({
        next: (data) => {
          this.results = data;
          this.reranking = false;
          // Auto-select active tab if the current one has no papers now
          if (this.results.groups[this.activeTabIndex]?.papers.length === 0) {
            this.autoSelectActiveTab();
          }
        },
        error: (err) => {
          this.error = err.error?.detail || 'Failed to re-rank papers.';
          this.reranking = false;
        },
      });
  }

  onThresholdSliderChange(value: number): void {
    this.similarityThreshold = value;
    this.triggerRerank();
  }

  onWeightSliderChange(value: number): void {
    this.similarityWeight = value;
    this.pagerankWeight = parseFloat((1 - value).toFixed(2));
    this.triggerRerank();
  }

  autoSelectActiveTab(): void {
    if (!this.results || this.results.groups.length === 0) return;
    const firstNonEmpty = this.results.groups.findIndex((g) => g.papers.length > 0);
    this.activeTabIndex = firstNonEmpty !== -1 ? firstNonEmpty : 0;
  }

  selectTab(index: number): void {
    this.activeTabIndex = index;
  }

  togglePaperDetails(doi: string): void {
    if (this.expandedPapers.has(doi)) {
      this.expandedPapers.delete(doi);
    } else {
      this.expandedPapers.add(doi);
    }
  }

  isPaperExpanded(doi: string): boolean {
    return this.expandedPapers.has(doi);
  }

  getAuthorsText(authors: string[]): string {
    if (!authors || authors.length === 0) return 'Unknown Authors';
    if (authors.length <= 3) return authors.join(', ');
    return authors.slice(0, 3).join(', ') + ' et al.';
  }

  onReset(): void {
    this.reset.emit();
  }
}
