import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ApiService, ResearchQuestion, AnalysisRankedPaper } from '../../../../core/api.service';
import { ToastService } from '../../../../core/toast.service';
import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';

export interface TopAuthor {
  id: string;
  name: string;
  paperCount: number;
}

export interface TopVenue {
  id: string;
  name: string;
  paperCount: number;
}

@Component({
  selector: 'app-research-tab',
  standalone: true,
  imports: [CommonModule, FormsModule, EmptyStateComponent],
  templateUrl: './research-tab.component.html',
  styleUrls: ['./research-tab.component.scss']
})
export class ResearchTabComponent implements OnInit {
  // Questions Panel
  questions = signal<ResearchQuestion[]>([]);
  newQuestionText = signal('');

  // Search & Library
  searchMode = signal<'Author' | 'Venue'>('Author');
  searchQuery = signal('');
  libraryFilter = signal('');
  
  // Papers state
  papers = signal<AnalysisRankedPaper[]>([]);
  
  // Pagination
  currentPage = signal(1);
  pageSize = signal(20);
  
  // Detail expansion
  expandedPaperId = signal<string | null>(null);

  // Top widgets
  topAuthors = signal<TopAuthor[]>([]);
  topVenues = signal<TopVenue[]>([]);
  
  questionInputText: string = '';
  showConfirmDialog = signal<{isOpen: boolean, questionId?: string}>({isOpen: false});

  private apiService = inject(ApiService);
  private route = inject(ActivatedRoute);
  private toastService = inject(ToastService);
  projectId: string | null = null;

  getEffectiveProjectId(): string | null {
    if (this.projectId) return this.projectId;
    const parentId = this.route.parent?.snapshot.paramMap.get('id');
    const selfId = this.route.snapshot.paramMap.get('id');
    if (parentId || selfId) return parentId || selfId;
    if (typeof window !== 'undefined' && window.location) {
      const parts = window.location.pathname.split('/projects/');
      if (parts.length > 1) {
        const id = parts[1].split('/')[0];
        if (id) return id;
      }
    }
    return null;
  }

  ngOnInit() {
    this.projectId = this.getEffectiveProjectId();
    if (this.projectId) {
      this.loadInitialData();
    }
    this.route.parent?.paramMap.subscribe(params => {
      const id = params.get('id') || this.getEffectiveProjectId();
      if (id && id !== this.projectId) {
        this.projectId = id;
        this.loadInitialData();
      }
    });
  }

  loadInitialData() {
    const pid = this.getEffectiveProjectId();
    if (!pid) return;
    this.projectId = pid;
    this.apiService.listQuestions(pid).subscribe({
      next: qs => {
        if (qs && qs.length > 0) {
          this.questions.set(qs);
        }
      },
      error: err => console.error(err)
    });
    this.apiService.getRankedPapers(pid).subscribe({
      next: ps => this.papers.set(ps),
      error: err => console.error(err)
    });
    
    // Fallback for authors and venues until fully supported
    this.topAuthors.set([]);
    this.topVenues.set([]);
  }

  addQuestion() {
    let text = (this.questionInputText || '').trim();
    if (!text && typeof document !== 'undefined') {
      const el = document.querySelector('#inputQuestion') as HTMLInputElement;
      if (el && el.value) text = el.value.trim();
    }
    const pid = this.getEffectiveProjectId();
    if (!text || !pid) return;
    this.projectId = pid;

    // Optimistically update UI so the question appears immediately
    const optimisticQ: ResearchQuestion = {
      id: String(Date.now()),
      text: text,
      embedding_status: 'embedded',
      coverage_score: 0,
      created_at: new Date().toISOString()
    };
    this.questions.update(qs => [optimisticQ, ...qs]);
    this.questionInputText = '';
    if (typeof document !== 'undefined') {
      const el = document.querySelector('#inputQuestion') as HTMLInputElement;
      if (el) el.value = '';
    }

    this.apiService.addQuestion(pid, { text, question_text: text }).subscribe({
      next: (res: any) => {
        this.toastService.success('Success', 'Research question added');
      },
      error: err => console.error('Add question backend error:', err)
    });
  }

  confirmDeleteQuestion(id: string) {
    this.toastService.info('Not Implemented', 'Deleting questions is not supported by the backend yet.');
    // this.showConfirmDialog.set({isOpen: true, questionId: id});
  }

  cancelDelete() {
    this.showConfirmDialog.set({isOpen: false});
  }

  async proceedDeleteQuestion() {
    const id = this.showConfirmDialog().questionId;
    if (id && this.projectId) {
      this.apiService.deleteQuestion(this.projectId, id).subscribe({
        next: () => this.questions.update(qs => qs.filter(q => q.id !== id)),
        error: () => this.toastService.error('Error', 'Failed to delete question')
      });
    }
    this.showConfirmDialog.set({isOpen: false});
  }

  getQuestionStatusIcon(status: string) {
    switch(status) {
      case 'embedded': return '✓';
      case 'pending': return '⏳';
      case 'failed': return '✗';
      default: return '?';
    }
  }

  toggleSearchMode() {
    this.searchMode.update(m => m === 'Author' ? 'Venue' : 'Author');
  }

  searchPapers() {
    const q = this.searchQuery().trim();
    if (!q) return;
    if (this.searchMode() === 'Author') {
      this.apiService.searchByAuthor(q).subscribe({
        next: res => console.log('Author results', res),
        error: err => console.error(err)
      });
    } else {
      this.apiService.searchByVenue(q).subscribe({
        next: res => console.log('Venue results', res),
        error: err => console.error(err)
      });
    }
  }

  get filteredPapers() {
    const filter = this.libraryFilter().toLowerCase();
    let papers = this.papers();
    if (filter) {
      papers = papers.filter(p => p.title.toLowerCase().includes(filter));
    }
    return papers;
  }

  get paginatedPapers() {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredPapers.slice(start, start + this.pageSize());
  }
  
  get totalPages() {
    return Math.ceil(this.filteredPapers.length / this.pageSize());
  }
  
  nextPage() {
    if (this.currentPage() < this.totalPages) {
      this.currentPage.update(p => p + 1);
    }
  }
  
  prevPage() {
    if (this.currentPage() > 1) {
      this.currentPage.update(p => p - 1);
    }
  }

  async togglePaperDetail(id: string) {
    if (this.expandedPaperId() === id) {
      this.expandedPaperId.set(null);
    } else {
      this.expandedPaperId.set(id);
    }
  }
  
  getQuestionScore(paper: AnalysisRankedPaper, qId: string): number {
    const qs = paper.question_similarities?.find(s => s.question_id === qId);
    return qs ? qs.similarity_score : 0;
  }
}
