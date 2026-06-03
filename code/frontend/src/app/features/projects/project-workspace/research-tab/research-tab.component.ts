import { Component, OnInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

export interface ResearchQuestion {
  id: string;
  text: string;
  status: 'embedded' | 'pending' | 'failed';
  coverage: number;
}

export interface Author {
  name: string;
  affiliation?: string;
}

export interface Paper {
  id: string;
  title: string;
  authors: Author[];
  year: number;
  venue: string;
  doi?: string;
  type?: string;
  abstract?: string;
  similarityScore: number;
  perQuestionScores?: Record<string, number>;
}

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

// Mock service for UI dev since ApiService is not fully wired
class MockApiService {
  listQuestions() { return Promise.resolve([{id: '1', text: 'How do LLMs reason?', status: 'embedded', coverage: 0.85} as ResearchQuestion]); }
  addQuestion(q: string) { return Promise.resolve({id: Math.random().toString(), text: q, status: 'pending', coverage: 0} as ResearchQuestion); }
  deleteQuestion(id: string) { return Promise.resolve(true); }
  searchByAuthor(a: string) { return Promise.resolve([]); }
  searchByVenue(v: string) { return Promise.resolve([]); }
  getPaperDetail(id: string) { return Promise.resolve({} as Paper); }
  getTopAuthors() { return Promise.resolve([{id: '1', name: 'John Doe', paperCount: 15} as TopAuthor]); }
  getTopVenues() { return Promise.resolve([{id: '1', name: 'Nature', paperCount: 20} as TopVenue]); }
}

import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-research-tab',
  standalone: true,
  imports: [CommonModule, FormsModule, EmptyStateComponent],
  templateUrl: './research-tab.component.html',
  styleUrls: ['./research-tab.component.scss'],
  providers: [MockApiService] // To be replaced with real ApiService
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
  papers = signal<Paper[]>([
    {
      id: 'p1',
      title: 'A Survey on Large Language Models',
      authors: [{name: 'Zhao et al.', affiliation: 'University of AI'}],
      year: 2023,
      venue: 'ArXiv',
      doi: '10.48550/arXiv.2303.18223',
      similarityScore: 0.92,
      abstract: 'Large Language Models (LLMs) have shown remarkable capabilities in natural language processing. This paper provides a comprehensive review of the recent advances in LLMs, discussing their architecture, training strategies, and evaluation metrics. We also highlight the challenges and future directions in this rapidly evolving field.',
      type: 'Journal Article',
      perQuestionScores: {'1': 0.95}
    },
    {
      id: 'p2',
      title: 'Attention Is All You Need',
      authors: [{name: 'Vaswani et al.', affiliation: 'Google'}],
      year: 2017,
      venue: 'NeurIPS',
      doi: '10.5555/3295222.3295349',
      similarityScore: 0.88,
      abstract: 'The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.',
      type: 'Conference Paper',
      perQuestionScores: {'1': 0.88}
    }
  ]);
  
  // Pagination
  currentPage = signal(1);
  pageSize = signal(20);
  
  // Detail expansion
  expandedPaperId = signal<string | null>(null);

  // Top widgets
  topAuthors = signal<TopAuthor[]>([]);
  topVenues = signal<TopVenue[]>([]);
  
  showConfirmDialog = signal<{isOpen: boolean, questionId?: string}>({isOpen: false});

  constructor(private apiService: MockApiService) {}

  ngOnInit() {
    this.loadInitialData();
  }

  async loadInitialData() {
    const [qs, authors, venues] = await Promise.all([
      this.apiService.listQuestions(),
      this.apiService.getTopAuthors(),
      this.apiService.getTopVenues()
    ]);
    this.questions.set(qs);
    this.topAuthors.set(authors);
    this.topVenues.set(venues);
  }

  async addQuestion() {
    const text = this.newQuestionText().trim();
    if (!text) return;
    const newQ = await this.apiService.addQuestion(text);
    this.questions.update(qs => [...qs, newQ]);
    this.newQuestionText.set('');
  }

  confirmDeleteQuestion(id: string) {
    this.showConfirmDialog.set({isOpen: true, questionId: id});
  }

  cancelDelete() {
    this.showConfirmDialog.set({isOpen: false});
  }

  async proceedDeleteQuestion() {
    const id = this.showConfirmDialog().questionId;
    if (id) {
      await this.apiService.deleteQuestion(id);
      this.questions.update(qs => qs.filter(q => q.id !== id));
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

  async searchPapers() {
    const q = this.searchQuery().trim();
    if (!q) return;
    let results: Paper[];
    if (this.searchMode() === 'Author') {
      results = await this.apiService.searchByAuthor(q);
    } else {
      results = await this.apiService.searchByVenue(q);
    }
    console.log('Search results', results);
  }

  get filteredPapers() {
    const filter = this.libraryFilter().toLowerCase();
    let papers = this.papers();
    if (filter) {
      papers = papers.filter(p => p.title.toLowerCase().includes(filter) || p.venue.toLowerCase().includes(filter));
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
  
  formatAuthors(authors: Author[]): string {
    return authors.map(a => a.name).join(', ');
  }
}
