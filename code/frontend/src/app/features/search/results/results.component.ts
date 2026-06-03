import { Component, Input, OnInit, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, GroupedResults, QuestionGroup, RankedPaper, Project, AddPapersToProjectRequest } from '../../../core/api.service';
import { ToastService } from '../../../core/toast.service';

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

  // Projects state
  projects: Project[] = [];
  selectedProjectId: string = '';
  selectedPaperDois: Set<string> = new Set<string>();
  importing: boolean = false;

  constructor(private api: ApiService, private toastService: ToastService) {}

  ngOnInit(): void {
    if (!this.results && this.sessionId) {
      this.loadResults();
    }
    this.loadProjects();
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

  loadProjects(): void {
    this.api.listProjects(false).subscribe({
      next: (res) => {
        this.projects = res.projects;
      },
      error: (err) => {
        console.error('Failed to load projects', err);
      }
    });
  }

  togglePaperSelection(doi: string, event: Event): void {
    event.stopPropagation();
    if (this.selectedPaperDois.has(doi)) {
      this.selectedPaperDois.delete(doi);
    } else {
      this.selectedPaperDois.add(doi);
    }
  }

  isPaperSelected(doi: string): boolean {
    return this.selectedPaperDois.has(doi);
  }

  importSelectedPapers(): void {
    if (!this.selectedProjectId || this.selectedPaperDois.size === 0) return;

    this.importing = true;
    const request: AddPapersToProjectRequest = {
      project_id: this.selectedProjectId,
      dois: Array.from(this.selectedPaperDois)
    };

    this.api.addPapersToProject(request).subscribe({
      next: (res) => {
        this.toastService.success('Import Successful', `Successfully imported ${this.selectedPaperDois.size} papers to project.`);
        this.selectedPaperDois.clear();
        this.importing = false;
      },
      error: (err) => {
        this.toastService.error('Import Failed', err.error?.detail || 'Failed to import papers to project.');
        this.importing = false;
      }
    });
  }

  onReset(): void {
    this.reset.emit();
  }
}
