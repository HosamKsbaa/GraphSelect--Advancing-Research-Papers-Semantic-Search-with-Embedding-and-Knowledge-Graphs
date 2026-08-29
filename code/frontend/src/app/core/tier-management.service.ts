import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap, catchError, throwError } from 'rxjs';
import { ApiService } from './api.service';

export interface ModelTier {
  id: string;
  name: string;
  description: string;
  model: string;
  temperature: number;
  top_p: number;
  max_output_tokens: number;
  color: string;
  is_system: boolean;
}

export interface TierCreateRequest {
  id?: string;
  name: string;
  description?: string;
  model: string;
  temperature?: number;
  top_p?: number;
  max_output_tokens?: number;
  color?: string;
}

export interface TierUpdateRequest {
  name?: string;
  description?: string;
  model?: string;
  temperature?: number;
  top_p?: number;
  max_output_tokens?: number;
  color?: string;
}

export interface TierListResponse {
  tiers: ModelTier[];
  total: number;
}

export interface TierDeleteResponse {
  status: string;
  tier_id: string;
  reassigned_agents_count: number;
  reassigned_to_tier_id: string;
  message?: string;
}

export const FALLBACK_SYSTEM_TIERS: ModelTier[] = [
  {
    id: 'tier1',
    name: 'Tier 1: Orchestration & Synthesis',
    description: 'High-reasoning orchestrators, section planners, critique rubrics, and diagnostic repair',
    model: 'gemini-2.5-flash',
    temperature: 0.7,
    top_p: 0.95,
    max_output_tokens: 8192,
    color: '#6366f1',
    is_system: true,
  },
  {
    id: 'tier2',
    name: 'Tier 2: Retrieval, Literature Crawlers & Draft Generation',
    description: 'High-throughput specialized workers for 1-hop GraphSelect BFS citation exploration, PageRank analysis, and drafting',
    model: 'gemini-3.5-flash-lite',
    temperature: 0.2,
    top_p: 0.95,
    max_output_tokens: 8192,
    color: '#10b981',
    is_system: true,
  },
  {
    id: 'tier3',
    name: 'Tier 3: Specialized Writing & Critique',
    description: 'Deep synthesis and academic writing generation with enhanced reasoning',
    model: 'gemini-2.5-pro',
    temperature: 0.5,
    top_p: 0.95,
    max_output_tokens: 16384,
    color: '#a855f7',
    is_system: true,
  },
];

@Injectable({ providedIn: 'root' })
export class TierManagementService {
  private http = inject(HttpClient);
  private api = inject(ApiService);

  // State Signals
  tiers = signal<ModelTier[]>(FALLBACK_SYSTEM_TIERS);
  loading = signal<boolean>(false);
  error = signal<string | null>(null);
  isEditorOpen = signal<boolean>(false);
  editingTier = signal<ModelTier | null>(null);

  // Computed Map for quick tier lookup
  tierMap = computed(() => {
    const map = new Map<string, ModelTier>();
    for (const t of this.tiers()) {
      map.set(t.id, t);
    }
    return map;
  });

  private get baseUrl(): string {
    return this.api.baseUrl;
  }

  loadTiers(): Observable<TierListResponse> {
    this.loading.set(true);
    this.error.set(null);
    return this.http.get<TierListResponse>(`${this.baseUrl}/agents/tiers`).pipe(
      tap((res) => {
        if (res.tiers && res.tiers.length > 0) {
          this.tiers.set(res.tiers);
        }
        this.loading.set(false);
      }),
      catchError((err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || err?.message || 'Failed to load model tiers');
        return throwError(() => err);
      })
    );
  }

  createTier(dto: TierCreateRequest): Observable<ModelTier> {
    this.loading.set(true);
    this.error.set(null);
    return this.http.post<ModelTier>(`${this.baseUrl}/agents/tiers`, dto).pipe(
      tap((created) => {
        this.tiers.update((list) => [...list.filter((t) => t.id !== created.id), created]);
        this.loading.set(false);
      }),
      catchError((err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || err?.message || 'Failed to create tier');
        return throwError(() => err);
      })
    );
  }

  updateTier(id: string, dto: TierUpdateRequest): Observable<ModelTier> {
    this.loading.set(true);
    this.error.set(null);
    return this.http.put<ModelTier>(`${this.baseUrl}/agents/tiers/${encodeURIComponent(id)}`, dto).pipe(
      tap((updated) => {
        this.tiers.update((list) => list.map((t) => (t.id === id ? updated : t)));
        this.loading.set(false);
      }),
      catchError((err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || err?.message || 'Failed to update tier');
        return throwError(() => err);
      })
    );
  }

  deleteTier(id: string): Observable<TierDeleteResponse> {
    this.loading.set(true);
    this.error.set(null);
    return this.http.delete<TierDeleteResponse>(`${this.baseUrl}/agents/tiers/${encodeURIComponent(id)}`).pipe(
      tap((res) => {
        this.tiers.update((list) => list.filter((t) => t.id !== id));
        this.loading.set(false);
      }),
      catchError((err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || err?.message || 'Failed to delete tier');
        return throwError(() => err);
      })
    );
  }

  getTierById(id: string): ModelTier | undefined {
    return this.tierMap().get(id) || this.tierMap().get('tier1') || this.tiers()[0];
  }

  openEditor(tier?: ModelTier): void {
    this.editingTier.set(tier || null);
    this.isEditorOpen.set(true);
  }

  closeEditor(): void {
    this.isEditorOpen.set(false);
    this.editingTier.set(null);
  }
}
