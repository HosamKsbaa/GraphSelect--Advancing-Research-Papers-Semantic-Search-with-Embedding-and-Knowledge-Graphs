import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs/operators';
import { ApiService, CoverageResult, AnalysisRankedPaper, CitationStats } from '../../../../core/api.service';
import { ToastService } from '../../../../core/toast.service';
import { LoadingIndicatorComponent } from '../../../../shared/loading-indicator/loading-indicator.component';
import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-analysis-tab',
  standalone: true,
  imports: [CommonModule, FormsModule, LoadingIndicatorComponent, EmptyStateComponent],
  templateUrl: './analysis-tab.component.html',
  styleUrls: ['./analysis-tab.component.scss']
})
export class AnalysisTabComponent implements OnInit {
  projectId: string | null = null;
  
  coverages: CoverageResult[] = [];
  rankedPapers: AnalysisRankedPaper[] = [];
  citationStats: CitationStats | null = null;
  
  isLoading = false;
  isGeneratingQueries = false;
  
  generatedQueries: Record<string, string[]> = {};

  constructor(
    private route: ActivatedRoute,
    private apiService: ApiService,
    private toastService: ToastService
  ) {}

  ngOnInit(): void {
    this.route.parent?.paramMap.subscribe(params => {
      this.projectId = params.get('id');
      if (this.projectId) {
        this.loadAnalysisData();
      }
    });
  }

  loadAnalysisData(): void {
    if (!this.projectId) return;
    
    this.isLoading = true;
    let completed = 0;
    
    const checkDone = () => {
      completed++;
      if (completed === 3) this.isLoading = false;
    };
    
    this.apiService.getCoverage(this.projectId).subscribe({
      next: (res) => { this.coverages = res.coverages; checkDone(); },
      error: (err) => { 
        this.toastService.error('Error loading coverage', err.message);
        checkDone();
      }
    });
    
    this.apiService.getRankedPapers(this.projectId).subscribe({
      next: (res) => { this.rankedPapers = res; checkDone(); },
      error: (err) => { 
        this.toastService.error('Error loading ranked papers', err.message);
        checkDone();
      }
    });
    
    this.apiService.getCitationStats(this.projectId).subscribe({
      next: (res) => { this.citationStats = res; checkDone(); },
      error: (err) => {
        // Stats might not exist if no papers
        if (err.status !== 404) {
           this.toastService.error('Error loading citation stats', err.message);
        }
        checkDone();
      }
    });
  }

  suggestQueries(questionId: string, questionText: string): void {
    if (!this.projectId) return;
    
    this.isGeneratingQueries = true;
    this.apiService.generateGapQueries(this.projectId, { gap_question: questionText, max_queries: 3 })
      .pipe(finalize(() => this.isGeneratingQueries = false))
      .subscribe({
        next: (res) => {
          this.generatedQueries[questionId] = res.queries;
          this.toastService.success('Queries generated', 'Gap queries successfully generated.');
        },
        error: (err) => this.toastService.error('Error', err.message)
      });
  }

  copyToClipboard(text: string): void {
    navigator.clipboard.writeText(text).then(() => {
      this.toastService.info('Copied', 'Query copied to clipboard');
    }).catch(() => {
      this.toastService.error('Copy Failed', 'Failed to copy text');
    });
  }
}
