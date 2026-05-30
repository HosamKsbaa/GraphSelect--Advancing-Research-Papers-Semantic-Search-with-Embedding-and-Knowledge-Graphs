import { Component, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, PaperSummary, SearchRequest, SearchResponse, ProgressEvent } from '../../core/api.service';

interface StreamEvent {
  type: string;
  message: string;
  progress: number;
  timestamp: Date;
}

@Component({
  selector: 'alrs-search',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './search.page.html',
  styleUrl: './search.page.scss',
})
export class SearchPage implements OnDestroy {
  // Step 1: Resolve title
  searchTitle = '';
  candidates: PaperSummary[] = [];
  selectedDoi = '';
  resolving = false;

  // Step 2: Research questions
  questions: string[] = [''];
  similarityThreshold = 0.5;
  maxDepth = 2;
  mode: 'interactive' | 'automated' = 'automated';

  // Step 3: Result
  searchResult: SearchResponse | null = null;
  searching = false;
  error = '';
  currentStep = 1;

  // Step 4: BFS streaming progress
  streamEvents: StreamEvent[] = [];
  streamProgress = 0;
  streamStatus: 'idle' | 'running' | 'complete' | 'failed' = 'idle';
  streamMessage = '';
  private eventSource: EventSource | null = null;

  constructor(private api: ApiService) {}

  ngOnDestroy(): void {
    this.closeStream();
  }

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
        // Automatically start BFS crawl
        this.startBfsStream(result.session_id);
      },
      error: (err) => {
        this.error = err.error?.detail || 'Search failed. Check the backend logs.';
        this.searching = false;
      },
    });
  }

  startBfsStream(sessionId: string): void {
    this.closeStream();
    this.streamEvents = [];
    this.streamProgress = 0;
    this.streamStatus = 'running';
    this.streamMessage = 'Connecting to search stream...';

    this.eventSource = this.api.createSearchStream(sessionId);

    // Listen for all event types
    const eventTypes = [
      'search_started', 'level_complete', 'embedding_progress',
      'cycle_results', 'ranking_complete', 'search_complete',
      'error_recovered', 'search_failed', 'throttled', 'progress',
    ];

    for (const eventType of eventTypes) {
      this.eventSource.addEventListener(eventType, (event: Event) => {
        const msgEvent = event as MessageEvent;
        try {
          const data: ProgressEvent = JSON.parse(msgEvent.data);
          this.streamProgress = data.progress_percent;
          this.streamMessage = data.message;

          this.streamEvents.push({
            type: data.event_type,
            message: data.message,
            progress: data.progress_percent,
            timestamp: new Date(),
          });

          if (data.event_type === 'search_complete') {
            this.streamStatus = 'complete';
            this.closeStream();
          } else if (data.event_type === 'search_failed') {
            this.streamStatus = 'failed';
            this.closeStream();
          }
        } catch (e) {
          console.warn('Failed to parse SSE event:', e);
        }
      });
    }

    // Handle generic message events
    this.eventSource.onmessage = (event: MessageEvent) => {
      try {
        const data: ProgressEvent = JSON.parse(event.data);
        this.streamProgress = data.progress_percent;
        this.streamMessage = data.message;
        this.streamEvents.push({
          type: data.event_type,
          message: data.message,
          progress: data.progress_percent,
          timestamp: new Date(),
        });
      } catch (e) {
        // Ignore parse errors for keepalive pings
      }
    };

    this.eventSource.onerror = () => {
      if (this.streamStatus === 'running') {
        this.streamStatus = 'failed';
        this.streamMessage = 'Connection to search stream lost.';
      }
      this.closeStream();
    };
  }

  private closeStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  resetSearch(): void {
    this.closeStream();
    this.currentStep = 1;
    this.searchResult = null;
    this.searchTitle = '';
    this.candidates = [];
    this.selectedDoi = '';
    this.questions = [''];
    this.streamEvents = [];
    this.streamProgress = 0;
    this.streamStatus = 'idle';
    this.streamMessage = '';
    this.error = '';
  }

  trackByIndex(index: number): number {
    return index;
  }
}
