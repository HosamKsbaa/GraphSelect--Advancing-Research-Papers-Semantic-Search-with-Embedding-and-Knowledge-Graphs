import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, PaperSummary, SearchRequest, SearchResponse } from '../../core/api.service';

@Component({
  selector: 'alrs-search',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './search.page.html',
  styleUrl: './search.page.scss',
})
export class SearchPage {
  // Step 1: Resolve title
  searchTitle = '';
  candidates: PaperSummary[] = [];
  selectedDoi = '';
  resolving = false;

  // Step 2: Research questions
  questions: string[] = [''];
  similarityThreshold = 0.5;
  maxDepth = 2;
  mode: 'interactive' | 'automated' = 'interactive';

  // Step 3: Result
  searchResult: SearchResponse | null = null;
  searching = false;
  error = '';
  currentStep = 1;

  constructor(private api: ApiService) {}

  resolveTitle(): void {
    if (!this.searchTitle.trim()) return;
    this.resolving = true;
    this.error = '';
    this.candidates = [];

    this.api.resolveTitle(this.searchTitle.trim()).subscribe({
      next: (papers) => {
        this.candidates = papers;
        this.resolving = false;
        if (papers.length === 0) {
          this.error = 'No papers found matching that title.';
        }
      },
      error: (err) => {
        this.error = 'Failed to search. Is the backend running?';
        this.resolving = false;
      },
    });
  }

  selectPaper(doi: string): void {
    this.selectedDoi = doi;
    this.currentStep = 2;
  }

  addQuestion(): void {
    if (this.questions.length < 6) {
      this.questions.push('');
    }
  }

  removeQuestion(index: number): void {
    if (this.questions.length > 1) {
      this.questions.splice(index, 1);
    }
  }

  startSearch(): void {
    const validQuestions = this.questions.filter((q) => q.trim().length > 0);
    if (validQuestions.length === 0) {
      this.error = 'Please enter at least one research question.';
      return;
    }

    this.searching = true;
    this.error = '';

    const request: SearchRequest = {
      seed_doi: this.selectedDoi,
      seed_title: null,
      research_questions: validQuestions,
      similarity_threshold: this.similarityThreshold,
      max_depth: this.maxDepth,
      mode: this.mode,
    };

    this.api.startSearch(request).subscribe({
      next: (result) => {
        this.searchResult = result;
        this.searching = false;
        this.currentStep = 3;
      },
      error: (err) => {
        this.error = err.error?.detail || 'Search failed. Check the backend logs.';
        this.searching = false;
      },
    });
  }

  trackByIndex(index: number): number {
    return index;
  }
}
