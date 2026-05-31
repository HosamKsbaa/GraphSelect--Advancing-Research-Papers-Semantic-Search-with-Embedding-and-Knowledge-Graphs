import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface HealthResponse {
  status: string;
  neo4j: string;
  mysql: string;
}

export interface PaperSummary {
  doi: string;
  title: string;
  year: number | null;
  cited_by_count: number;
  authors: string[];
}

export interface SearchRequest {
  seed_doi: string | null;
  seed_title: string | null;
  research_questions: string[];
  similarity_threshold: number;
  max_depth: number;
  mode: 'interactive' | 'automated';
}

export interface SearchResponse {
  session_id: string;
  status: string;
  seed_paper_doi: string;
  message: string;
}

export interface Session {
  session_id: string;
  seed_doi: string;
  research_questions: string[];
  similarity_threshold: number;
  max_depth: number;
  mode: string;
  status: string;
  papers_discovered: number;
  papers_relevant: number;
  current_depth: number;
  created_at: string;
  updated_at: string | null;
}

export interface SessionList {
  sessions: Session[];
  total: number;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly baseUrl = '/api';

  constructor(private http: HttpClient) {}

  // --- Health ---
  getHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.baseUrl}/health`);
  }

  getVersion(): Observable<{ version: string }> {
    return this.http.get<{ version: string }>(`${this.baseUrl}/version`);
  }

  // --- Search ---
  resolveTitle(title: string, maxResults = 10): Observable<PaperSummary[]> {
    return this.http.post<PaperSummary[]>(
      `${this.baseUrl}/search/resolve-title?title=${encodeURIComponent(title)}&max_results=${maxResults}`,
      {},
    );
  }

  startSearch(request: SearchRequest): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(`${this.baseUrl}/search/start`, request);
  }

  // --- Sessions ---
  listSessions(): Observable<SessionList> {
    return this.http.get<SessionList>(`${this.baseUrl}/sessions`);
  }

  getSession(sessionId: string): Observable<Session> {
    return this.http.get<Session>(`${this.baseUrl}/sessions/${sessionId}`);
  }

  deleteSession(sessionId: string): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.baseUrl}/sessions/${sessionId}`);
  }

  // --- SSE Streaming ---
  /**
   * Subscribe to BFS crawl progress events via Server-Sent Events.
   * Returns an EventSource that emits ProgressEvent objects.
   */
  createSearchStream(sessionId: string): EventSource {
    return new EventSource(`${this.baseUrl}/search/${sessionId}/stream`);
  }

  // --- Results and Re-ranking ---
  getResults(sessionId: string, similarityWeight = 0.7, pagerankWeight = 0.3): Observable<GroupedResults> {
    return this.http.get<GroupedResults>(
      `${this.baseUrl}/search/${sessionId}/results?similarity_weight=${similarityWeight}&pagerank_weight=${pagerankWeight}`
    );
  }

  rerank(
    sessionId: string,
    similarityThreshold: number,
    similarityWeight = 0.7,
    pagerankWeight = 0.3
  ): Observable<GroupedResults> {
    return this.http.post<GroupedResults>(
      `${this.baseUrl}/search/${sessionId}/rerank`,
      {
        similarity_threshold: similarityThreshold,
        similarity_weight: similarityWeight,
        pagerank_weight: pagerankWeight
      }
    );
  }

  // --- Logs ---
  getAppLogs(
    level?: string,
    module?: string,
    sessionId?: string,
    limit = 100
  ): Observable<AppLog[]> {
    let params = `limit=${limit}&_t=${new Date().getTime()}`;
    if (level) params += `&level=${encodeURIComponent(level)}`;
    if (module) params += `&module=${encodeURIComponent(module)}`;
    if (sessionId) params += `&session_id=${encodeURIComponent(sessionId)}`;
    return this.http.get<AppLog[]>(`${this.baseUrl}/logs?${params}`);
  }

  getApiLogs(
    service?: string,
    sessionId?: string,
    limit = 100
  ): Observable<ApiLog[]> {
    let params = `limit=${limit}&_t=${new Date().getTime()}`;
    if (service) params += `&service=${encodeURIComponent(service)}`;
    if (sessionId) params += `&session_id=${encodeURIComponent(sessionId)}`;
    return this.http.get<ApiLog[]>(`${this.baseUrl}/logs/api-requests?${params}`);
  }

  // --- Debug ---
  debugTestRetrieve(doi: string): Observable<DebugRetrieveResponse> {
    return this.http.post<DebugRetrieveResponse>(
      `${this.baseUrl}/debug/test-retrieve`,
      { doi }
    );
  }

  debugTestEmbed(text: string): Observable<DebugEmbedResponse> {
    return this.http.post<DebugEmbedResponse>(
      `${this.baseUrl}/debug/test-embed`,
      { text }
    );
  }

  debugTestSimilarity(textA: string, textB: string): Observable<DebugSimilarityResponse> {
    return this.http.post<DebugSimilarityResponse>(
      `${this.baseUrl}/debug/test-similarity`,
      { text_a: textA, text_b: textB }
    );
  }

  // --- Settings ---
  getSettings(): Observable<SettingsResponse> {
    return this.http.get<SettingsResponse>(`${this.baseUrl}/settings`);
  }

  updateSettings(body: SettingsUpdateRequest): Observable<SettingsUpdateResponse> {
    return this.http.put<SettingsUpdateResponse>(`${this.baseUrl}/settings`, body);
  }
}

export interface ProgressEvent {
  event_type: string;
  session_id: string;
  timestamp: string;
  progress_percent: number;
  message: string;
  data?: Record<string, unknown>;
}

export interface AppLog {
  id: number;
  session_id: string | null;
  level: string;
  module: string;
  message: string;
  extra: Record<string, unknown> | null;
  created_at: string;
}

export interface ApiLog {
  id: number;
  session_id: string | null;
  service: string;
  method: string;
  url: string;
  status_code: number | null;
  response_time_ms: number | null;
  payload_summary: string | null;
  request_body?: string | null;
  response_body?: string | null;
  created_at: string;
}

export interface RankedPaper {
  doi: string;
  title: string;
  year: number | null;
  cited_by_count: number;
  similarity_score: number;
  pagerank_score: number;
  hybrid_score: number;
  question_group: string;
  abstract_snippet: string | null;
  authors: string[];
}

export interface QuestionGroup {
  question: string;
  papers: RankedPaper[];
  avg_similarity: number;
  paper_count: number;
}

export interface GroupedResults {
  session_id: string;
  groups: QuestionGroup[];
  total_papers: number;
  similarity_threshold: number;
  similarity_weight: number;
  pagerank_weight: number;
}

// --- Debug interfaces ---
export interface DebugRetrieveResponse {
  success: boolean;
  doi?: string;
  title?: string;
  abstract?: string;
  year?: number;
  cited_by_count?: number;
  elapsed_ms: number;
  error?: string;
}

export interface DebugEmbedResponse {
  success: boolean;
  dimensions?: number;
  first_5_values?: number[];
  elapsed_ms: number;
  error?: string;
}

export interface DebugSimilarityResponse {
  success: boolean;
  similarity_score?: number;
  dimensions?: number;
  elapsed_ms: number;
  error?: string;
}

// --- Settings interfaces ---
export interface SettingsResponse {
  gemini_api_key_set: boolean;
  gemini_api_key_preview: string;
  openalex_api_key_set: boolean;
  openalex_api_key_preview: string;
  openalex_email: string;
  embedding_model: string;
  embedding_dimensions: number;
}

export interface SettingsUpdateRequest {
  gemini_api_key?: string;
  openalex_api_key?: string;
  openalex_email?: string;
}

export interface SettingsUpdateResponse {
  success: boolean;
  message: string;
  restart_required: boolean;
}
