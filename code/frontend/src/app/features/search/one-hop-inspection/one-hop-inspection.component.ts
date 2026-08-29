import { Component, Input, Output, EventEmitter, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CandidatePaperState,
  SteeringActionOption,
  OneHopExpansionResult,
  PaperSummary,
  Project,
  AddPapersToProjectRequest,
  ApiService
} from '../../../core/api.service';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'alrs-one-hop-inspection',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './one-hop-inspection.component.html',
  styleUrl: './one-hop-inspection.component.scss',
})
export class OneHopInspectionComponent {
  // Inputs
  @Input() seedPaper: PaperSummary | null = null;
  @Input() seedDoi: string = '';
  @Input() seedTitle: string = '';
  @Input() questions: string[] = [];
  @Input() similarityThreshold: number = 0.5;
  @Input() currentLevel: number = 1;
  @Input() isPreflight: boolean = false;
  @Input() isRunning: boolean = false;
  @Input() isPaused: boolean = false;
  @Input() sessionId: string = '';
  @Input() projects: Project[] = [];
  @Input() selectedProjectId: string = '';

  private _candidates = signal<CandidatePaperState[]>([]);
  @Input() set candidates(value: CandidatePaperState[]) {
    this._candidates.set(value || []);
  }
  get candidates(): CandidatePaperState[] {
    return this._candidates();
  }

  private _expansionResult = signal<OneHopExpansionResult | null>(null);
  @Input() set expansionResult(value: OneHopExpansionResult | null) {
    this._expansionResult.set(value);
    if (value && value.candidates) {
      this._candidates.set(value.candidates);
    }
  }
  get expansionResult(): OneHopExpansionResult | null {
    return this._expansionResult();
  }

  // Outputs
  @Output() start1Hop = new EventEmitter<void>();
  @Output() addToProject = new EventEmitter<CandidatePaperState>();
  @Output() expand1Hop = new EventEmitter<CandidatePaperState>();
  @Output() branchSeed = new EventEmitter<CandidatePaperState>();
  @Output() concludeSynthesize = new EventEmitter<void>();
  @Output() batchExpand = new EventEmitter<CandidatePaperState[]>();
  @Output() resetSearch = new EventEmitter<void>();
  @Output() selectProject = new EventEmitter<string>();

  // Filter and Sort state
  directionFilter = signal<string>('all');
  statusFilter = signal<string>('all');
  partitionFilter = signal<string>('all');
  sortBy = signal<string>('similarity');
  filterSearch = signal<string>('');
  activeThreshold = signal<number>(0.5);

  // Expanded abstract drawers
  expandedAbstracts = signal<Set<string>>(new Set());

  // Selected candidates for batch actions
  selectedDois = signal<Set<string>>(new Set());

  // Locally added to project DOIs
  addedToProjectDois = signal<Set<string>>(new Set());

  constructor(private api: ApiService, private toast: ToastService) {}

  // Filtered & Sorted Candidates
  filteredCandidates = computed(() => {
    let list = this._candidates();
    const dir = this.directionFilter();
    const stat = this.statusFilter();
    const part = this.partitionFilter();
    const q = this.filterSearch().trim().toLowerCase();
    const thresh = this.activeThreshold();

    // Direction filter
    if (dir !== 'all') {
      if (dir === 'forward') {
        list = list.filter(c => c.direction === 'forward_citation' || c.direction === 'both');
      } else if (dir === 'backward') {
        list = list.filter(c => c.direction === 'backward_reference' || c.direction === 'both');
      }
    }

    // Status filter
    if (stat !== 'all') {
      if (stat === 'in_library') {
        list = list.filter(c => c.already_in_library || this.addedToProjectDois().has(c.doi));
      } else if (stat === 'not_in_library') {
        list = list.filter(c => !c.already_in_library && !this.addedToProjectDois().has(c.doi));
      }
    }

    // Partition filter
    if (part !== 'all') {
      list = list.filter(c => c.partition === part);
    }

    // Search query filter
    if (q) {
      list = list.filter(c =>
        c.title.toLowerCase().includes(q) ||
        c.doi.toLowerCase().includes(q) ||
        (c.authors && c.authors.some(a => a.toLowerCase().includes(q))) ||
        (c.venue && c.venue.toLowerCase().includes(q))
      );
    }

    // Threshold filter
    if (thresh > 0) {
      list = list.filter(c => (c.max_similarity ?? c.mean_similarity ?? 0) >= thresh);
    }

    // Sorting
    const sort = this.sortBy();
    return [...list].sort((a, b) => {
      if (sort === 'similarity') {
        return (b.max_similarity ?? b.mean_similarity ?? 0) - (a.max_similarity ?? a.mean_similarity ?? 0);
      } else if (sort === 'pagerank') {
        return (b.pagerank_score ?? 0) - (a.pagerank_score ?? 0);
      } else if (sort === 'citations') {
        return (b.citation_count ?? 0) - (a.citation_count ?? 0);
      } else if (sort === 'year') {
        return (b.year ?? 0) - (a.year ?? 0);
      }
      return 0;
    });
  });

  // Derived Stats
  totalDiscovered = computed(() => {
    const res = this._expansionResult();
    if (res) return res.total_discovered;
    return this._candidates().length;
  });

  totalNew = computed(() => {
    const res = this._expansionResult();
    if (res) return res.total_new;
    return this._candidates().filter(c => !c.already_in_library).length;
  });

  avgSimilarity = computed(() => {
    const list = this._candidates();
    if (list.length === 0) return 0;
    const sum = list.reduce((acc, c) => acc + (c.mean_similarity ?? c.max_similarity ?? 0), 0);
    return sum / list.length;
  });

  strategicRecommendation = computed(() => {
    const res = this._expansionResult();
    return res?.strategic_recommendation || '';
  });

  steeringOptions = computed(() => {
    const res = this._expansionResult();
    return res?.steering_options || [];
  });

  // Abstract drawer toggle
  toggleAbstract(doi: string): void {
    this.expandedAbstracts.update(set => {
      const next = new Set(set);
      if (next.has(doi)) {
        next.delete(doi);
      } else {
        next.add(doi);
      }
      return next;
    });
  }

  isAbstractExpanded(doi: string): boolean {
    return this.expandedAbstracts().has(doi);
  }

  // Selection toggle for batch operations
  toggleSelection(doi: string, event: Event): void {
    event.stopPropagation();
    this.selectedDois.update(set => {
      const next = new Set(set);
      if (next.has(doi)) {
        next.delete(doi);
      } else {
        next.add(doi);
      }
      return next;
    });
  }

  isCandidateSelected(doi: string): boolean {
    return this.selectedDois().has(doi);
  }

  selectAllVisible(): void {
    const visible = this.filteredCandidates();
    this.selectedDois.set(new Set(visible.map(c => c.doi)));
  }

  clearSelection(): void {
    this.selectedDois.set(new Set());
  }

  // Actions
  onStart1Hop(): void {
    this.start1Hop.emit();
  }

  onAddCandidateToProject(candidate: CandidatePaperState, event?: Event): void {
    if (event) event.stopPropagation();
    this.addedToProjectDois.update(set => {
      const next = new Set(set);
      next.add(candidate.doi);
      return next;
    });
    this.addToProject.emit(candidate);
  }

  onExpand1HopDeeper(candidate: CandidatePaperState, event?: Event): void {
    if (event) event.stopPropagation();
    this.expand1Hop.emit(candidate);
  }

  onBranchAsSeed(candidate: CandidatePaperState, event?: Event): void {
    if (event) event.stopPropagation();
    this.branchSeed.emit(candidate);
  }

  onConcludeAndSynthesize(): void {
    this.concludeSynthesize.emit();
  }

  onBatchExpandSelected(): void {
    const selected = this._candidates().filter(c => this.selectedDois().has(c.doi));
    if (selected.length > 0) {
      this.batchExpand.emit(selected);
    }
  }

  onReset(): void {
    this.resetSearch.emit();
  }

  onSteeringOptionClick(option: SteeringActionOption): void {
    if (option.action_type === 'expand_deeper' && option.target_doi) {
      const cand = this._candidates().find(c => c.doi === option.target_doi);
      if (cand) {
        this.expand1Hop.emit(cand);
        return;
      }
      // Create minimal candidate state
      this.expand1Hop.emit({
        doi: option.target_doi,
        title: option.target_title || option.target_doi,
        authors: [],
        year: null,
        venue: null,
        abstract_snippet: '',
        direction: 'forward_citation',
        citation_count: 0,
        in_graph_degree: 1,
        similarity_scores: [],
        max_similarity: 0.8,
        mean_similarity: 0.8,
        already_in_library: false,
        embedding_cached: true,
        pagerank_score: 0.5
      });
    } else if (option.action_type === 'add_to_library' && option.target_doi) {
      const cand = this._candidates().find(c => c.doi === option.target_doi);
      if (cand) {
        this.onAddCandidateToProject(cand);
      }
    } else if (option.action_type === 'conclude') {
      this.onConcludeAndSynthesize();
    }
  }

  getAuthorsSummary(authors: string[]): string {
    if (!authors || authors.length === 0) return 'Unknown Authors';
    if (authors.length <= 3) return authors.join(', ');
    return `${authors.slice(0, 3).join(', ')} et al.`;
  }

  getSimilarityPercent(score: number | undefined): string {
    if (score === undefined || score === null) return '0%';
    return `${Math.round(score * 100)}%`;
  }

  getPartitionLabel(partition?: string | null): string {
    if (!partition) return '';
    if (partition === 'foundational_prior_art') return '🏛️ Foundational Prior Art';
    if (partition === 'contemporary_breakthroughs') return '🚀 Contemporary Breakthrough';
    if (partition === 'topological_bridges') return '🌉 Topological Bridge';
    return partition;
  }
}
