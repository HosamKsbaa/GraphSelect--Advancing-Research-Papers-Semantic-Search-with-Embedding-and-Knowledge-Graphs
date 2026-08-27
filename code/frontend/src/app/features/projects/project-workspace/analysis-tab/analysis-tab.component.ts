import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs/operators';
import { ApiService, CoverageResult, AnalysisRankedPaper, CitationStats } from '../../../../core/api.service';
import { ToastService } from '../../../../core/toast.service';
import { AuthModalService } from '../../../../core/auth-modal.service';
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
  private route = inject(ActivatedRoute);
  private apiService = inject(ApiService);
  private toastService = inject(ToastService);
  public authModalService = inject(AuthModalService);

  projectId: string | null = null;
  
  coverages: CoverageResult[] = [];
  rankedPapers: AnalysisRankedPaper[] = [];
  citationStats: CitationStats | null = null;
  
  isLoading = false;
  isGeneratingQueries = false;
  
  generatedQueries: Record<string, string[]> = {};

  getEffectiveProjectId(): string {
    const parentId = this.route.parent?.snapshot.paramMap.get('id');
    const selfId = this.route.snapshot.paramMap.get('id');
    if (parentId || selfId) return parentId || selfId || '';
    if (typeof window !== 'undefined' && window.location) {
      const parts = window.location.pathname.split('/projects/');
      if (parts.length > 1) {
        const id = parts[1].split('/')[0];
        if (id) return id;
      }
    }
    return '';
  }

  ngOnInit(): void {
    const pid = this.getEffectiveProjectId();
    if (pid) {
      this.projectId = pid;
      this.loadAnalysisData();
    }
    this.route.parent?.paramMap.subscribe(params => {
      const id = params.get('id') || this.getEffectiveProjectId();
      if (id && id !== this.projectId) {
        this.projectId = id;
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

    if (!this.authModalService.hasValidCredentials()) {
      this.toastService.warning(
        'Credentials Required',
        'Please configure your Gemini API Key or Vertex AI credentials to generate gap-filling queries.'
      );
      this.authModalService.open();
      return;
    }
    
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
