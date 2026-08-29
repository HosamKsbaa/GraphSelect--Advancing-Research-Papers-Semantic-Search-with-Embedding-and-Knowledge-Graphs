import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  ApiService,
  PaperSummary,
  SearchRequest,
  SearchResponse,
  ProgressEvent,
  CandidatePaperState,
  OneHopExpansionResult,
  Project,
  AddPapersToProjectRequest
} from '../../core/api.service';
import { ToastService } from '../../core/toast.service';
import { ResultsComponent } from './results/results.component';
import { OneHopInspectionComponent } from './one-hop-inspection/one-hop-inspection.component';

interface StreamEvent {
  type: string;
  message: string;
  progress: number;
  timestamp: Date;
}

@Component({
  selector: 'alrs-search',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ResultsComponent, OneHopInspectionComponent],
  templateUrl: './search.page.html',
  styleUrl: './search.page.scss',
})
export class SearchPage implements OnInit, OnDestroy {
  // Step 1: Resolve title
  searchTitle = 'GraphSelect: Embedding-Guided Graph Traversal for Scalable Semantic Paper Search';
  candidates: PaperSummary[] = [];
  selectedDoi = '';
  selectedSeedPaper: PaperSummary | null = null;
  resolving = false;

  // Step 2: Research questions
  questions: string[] = [
    'How does selective graph expansion compare to full vector database indexes?',
    'What is the performance benefit of combining cosine similarity with PageRank?'
  ];
  similarityThreshold = 0.5;
  maxDepth = 2;
  mode: 'interactive' | 'automated' = 'automated';

  // Step 3: Result & 1-Hop Inspection State
  searchResult: SearchResponse | null = null;
  searching = false;
  error = '';
  currentStep = 1;

  // 1-Hop HITL Traversal State
  cycleCandidates: CandidatePaperState[] = [];
  cycleResults: OneHopExpansionResult | null = null;
  currentCycleLevel = 1;
  isCyclePaused = false;
  projects: Project[] = [];
  selectedProjectId = '';

  // Step 4: BFS streaming progress
  streamEvents: StreamEvent[] = [];
  streamProgress = 0;
  streamStatus: 'idle' | 'running' | 'complete' | 'failed' = 'idle';
  streamMessage = '';
  private eventSource: EventSource | null = null;
  private readonly SSE_EVENT_TYPES = [
    'search_started', 'level_complete', 'embedding_progress',
    'cycle_results', 'ranking_complete', 'search_complete',
    'error_recovered', 'search_failed', 'throttled', 'progress',
    'LEVEL_COMPLETE', 'EMBEDDING_PROGRESS'
  ];

  constructor(private api: ApiService, private toast: ToastService) {}

  ngOnInit(): void {
    this.loadProjects();
  }

  ngOnDestroy(): void {
    this.closeStream();
  }

  loadProjects(): void {
    this.api.listProjects().subscribe({
      next: (projects) => {
        this.projects = projects;
        if (projects.length > 0) {
          this.selectedProjectId = projects[0].id;
        }
      },
      error: () => {}
    });
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
    this.selectedSeedPaper = this.candidates.find(c => c.doi === doi) || {
      doi: doi,
      title: this.searchTitle,
      year: null,
      cited_by_count: 0,
      authors: []
    };
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
    this.cycleCandidates = [];
    this.cycleResults = null;
    this.isCyclePaused = false;
    this.currentCycleLevel = 1;

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

  private handleSseEvent = (event: Event) => {
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

      const eventTypeLower = data.event_type.toLowerCase();

      if (eventTypeLower === 'cycle_results' || eventTypeLower === 'level_complete') {
        const payloadData = (data.data || {}) as any;
        if (payloadData.candidates && Array.isArray(payloadData.candidates)) {
          this.cycleCandidates = payloadData.candidates;
        } else if (payloadData.top_papers && Array.isArray(payloadData.top_papers)) {
          this.cycleCandidates = payloadData.top_papers.map((p: any) => ({
            doi: p.doi || '',
            title: p.title || '',
            authors: p.authors || [],
            year: p.year || null,
            venue: p.venue || null,
            abstract_snippet: p.abstract_snippet || p.abstract || '',
            direction: p.direction || 'forward_citation',
            citation_count: p.citation_count || p.cited_by_count || 0,
            in_graph_degree: p.in_graph_degree || 1,
            similarity_scores: p.similarity_scores || [],
            max_similarity: p.max_similarity || p.similarity_score || 0.8,
            mean_similarity: p.mean_similarity || p.similarity_score || 0.8,
            already_in_library: p.already_in_library || false,
            embedding_cached: p.embedding_cached !== false,
            pagerank_score: p.pagerank_score || 0.5,
            partition: p.partition || null,
            recommendation_rationale: p.recommendation_rationale || ''
          }));
        }

        this.currentCycleLevel = payloadData.level || this.currentCycleLevel;
        this.cycleResults = {
          seed_doi: this.selectedDoi,
          seed_title: this.selectedSeedPaper?.title || this.searchTitle,
          cycle_level: this.currentCycleLevel,
          total_discovered: payloadData.papers_discovered || this.cycleCandidates.length,
          total_new: payloadData.papers_new || this.cycleCandidates.length,
          candidates: this.cycleCandidates,
          strategic_recommendation: payloadData.strategic_recommendation || '',
          steering_options: payloadData.steering_options || []
        };

        if (this.mode === 'interactive') {
          this.isCyclePaused = true;
        }
      } else if (eventTypeLower === 'search_complete') {
        this.streamStatus = 'complete';
        this.closeStream();
        // If automated or no candidates were inspected, move to step 4
        if (this.mode === 'automated' && this.cycleCandidates.length === 0) {
          this.currentStep = 4;
        }
      } else if (eventTypeLower === 'search_failed') {
        this.streamStatus = 'failed';
        this.closeStream();

        if (data.message.includes('400') || data.message.toLowerCase().includes('api key')) {
          this.toast.error(
            'Invalid API Key', 'The Gemini API returned a 400 error.', 10000,
            { label: 'Go to Settings', routerLink: '/settings' }
          );
        } else {
          this.toast.error('Search Failed', data.message);
        }
      }
    } catch (e) {
      console.warn('Failed to parse SSE event:', e);
    }
  };

  private handleSseMessage = (event: MessageEvent) => {
    try {
      const data: ProgressEvent = JSON.parse(event.data);
      this.streamProgress = data.progress_percent;
      this.streamMessage = data.message;
      this.streamEvents.push({
        type: data.event_type,
        message: data.message,
        progress: data.progress_percent,
        timestamp: new Date()
      });
    } catch (e) {}
  };

  private handleSseError = () => {
    if (this.streamStatus === 'running') {
      this.streamStatus = 'failed';
      this.streamMessage = 'Connection to search stream lost.';
    }
    this.closeStream();
  };

  startBfsStream(sessionId: string): void {
    this.closeStream();
    this.streamEvents = [];
    this.streamProgress = 0;
    this.streamStatus = 'running';
    this.streamMessage = 'Connecting to search stream...';

    this.eventSource = this.api.createSearchStream(sessionId);
    for (const eventType of this.SSE_EVENT_TYPES) {
      this.eventSource.addEventListener(eventType, this.handleSseEvent);
    }
    this.eventSource.onmessage = this.handleSseMessage;
    this.eventSource.onerror = this.handleSseError;
  }

  private closeStream(): void {
    if (this.eventSource) {
      for (const eventType of this.SSE_EVENT_TYPES) {
        this.eventSource.removeEventListener(eventType, this.handleSseEvent);
      }
      this.eventSource.onmessage = null;
      this.eventSource.onerror = null;
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  // 1-Hop Steering Handlers
  handleAddToProject(candidate: CandidatePaperState): void {
    if (!this.selectedProjectId) {
      this.toast.success('Added to Library', `Paper ${candidate.doi} marked in library.`);
      return;
    }

    const req: AddPapersToProjectRequest = {
      project_id: this.selectedProjectId,
      dois: [candidate.doi]
    };

    this.api.addPapersToProject(req).subscribe({
      next: () => {
        this.toast.success('Import Successful', `Added "${candidate.title}" to project library.`);
      },
      error: (err) => {
        this.toast.error('Import Failed', err.error?.detail || 'Could not import paper to project.');
      }
    });
  }

  handleExpand1Hop(candidate: CandidatePaperState): void {
    if (!this.searchResult?.session_id) return;
    this.toast.info('Expanding 1-Hop', `Enqueuing ${candidate.title} for next 1-hop traversal...`);
    this.isCyclePaused = false;
    this.currentCycleLevel += 1;

    this.api.enqueuePapers(this.searchResult.session_id, [candidate.doi]).subscribe({
      next: () => {
        this.toast.success('Hop Enqueued', `Starting 1-hop traversal from ${candidate.doi}.`);
      },
      error: (err) => {
        console.warn('Enqueue notice:', err);
      }
    });
  }

  handleBranchSeed(candidate: CandidatePaperState): void {
    this.selectedDoi = candidate.doi;
    this.searchTitle = candidate.title;
    this.selectedSeedPaper = {
      doi: candidate.doi,
      title: candidate.title,
      year: candidate.year,
      cited_by_count: candidate.citation_count,
      authors: candidate.authors
    };
    this.currentStep = 2;
    this.toast.info('Seed Branched', `Search re-anchored on ${candidate.title}.`);
  }

  handleConcludeSynthesize(): void {
    this.currentStep = 4;
  }

  handleBatchExpand(candidates: CandidatePaperState[]): void {
    if (!this.searchResult?.session_id) return;
    const dois = candidates.map(c => c.doi);
    this.isCyclePaused = false;
    this.currentCycleLevel += 1;

    this.api.enqueuePapers(this.searchResult.session_id, dois).subscribe({
      next: () => {
        this.toast.success('Batch Enqueued', `Enqueued ${dois.length} papers for next traversal step.`);
      },
      error: (err) => {
        console.warn('Batch enqueue notice:', err);
      }
    });
  }

  resetSearch(): void {
    this.closeStream();
    this.currentStep = 1;
    this.searchResult = null;
    this.searchTitle = 'GraphSelect: Embedding-Guided Graph Traversal for Scalable Semantic Paper Search';
    this.candidates = [];
    this.selectedDoi = '';
    this.selectedSeedPaper = null;
    this.cycleCandidates = [];
    this.cycleResults = null;
    this.isCyclePaused = false;
    this.currentCycleLevel = 1;
    this.questions = [
      'How does selective graph expansion compare to full vector database indexes?',
      'What is the performance benefit of combining cosine similarity with PageRank?'
    ];
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
