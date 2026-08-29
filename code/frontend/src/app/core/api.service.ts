import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

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

export interface CandidateSimilarityScore {
  question_id?: string;
  question?: string;
  question_text?: string;
  similarity_score?: number;
  score?: number;
}

export interface CandidatePaperState {
  doi: string;
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  abstract_snippet: string;
  direction: 'forward_citation' | 'backward_reference' | 'both' | string;
  citation_count: number;
  in_graph_degree: number;
  similarity_scores: CandidateSimilarityScore[];
  max_similarity: number;
  mean_similarity: number;
  already_in_library: boolean;
  embedding_cached: boolean;
  pagerank_score: number;
  partition?: 'foundational_prior_art' | 'contemporary_breakthroughs' | 'topological_bridges' | string | null;
  archetype_scores?: Record<string, number>;
  recommendation_rationale?: string;
  primary_rq?: string;
}

export interface SteeringActionOption {
  option_id: string;
  action_type: 'expand_deeper' | 'add_to_library' | 'branch_seed' | 'conclude' | string;
  target_doi?: string | null;
  target_title?: string | null;
  label: string;
  rationale: string;
}

export interface OneHopExpansionResult {
  seed_doi: string;
  seed_title: string;
  cycle_level: number;
  total_discovered: number;
  total_new: number;
  forward_count?: number;
  backward_count?: number;
  both_count?: number;
  candidates: CandidatePaperState[];
  new_dois?: string[];
  traversal_summary?: string[];
  errors?: string[];
  strategic_recommendation?: string;
  steering_options?: SteeringActionOption[];
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
  get baseUrl(): string {
    return localStorage.getItem('alrs_api_base_url') || '/api';
  }

  setBaseUrl(url: string): void {
    const cleanUrl = url.trim().replace(/\/$/, '');
    if (cleanUrl) {
      localStorage.setItem('alrs_api_base_url', cleanUrl);
    } else {
      localStorage.removeItem('alrs_api_base_url');
    }
  }

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

  enqueuePapers(sessionId: string, dois: string[]): Observable<{ enqueued: number; status: string; session_id: string }> {
    return this.http.post<{ enqueued: number; status: string; session_id: string }>(
      `${this.baseUrl}/search/${sessionId}/enqueue`,
      dois
    );
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

  // --- Settings & Auth ---
  getSettings(): Observable<SettingsResponse> {
    return this.http.get<SettingsResponse>(`${this.baseUrl}/settings`);
  }

  getAvailableModels(apiKey?: string, mode?: string): Observable<AvailableModelsResponse> {
    const params: string[] = [];
    if (apiKey) params.push(`gemini_api_key=${encodeURIComponent(apiKey)}`);
    if (mode) params.push(`mode=${encodeURIComponent(mode)}`);
    const query = params.length > 0 ? `?${params.join('&')}` : '';
    return this.http.get<AvailableModelsResponse>(`${this.baseUrl}/settings/models${query}`);
  }

  updateSettings(body: SettingsUpdateRequest): Observable<SettingsUpdateResponse> {
    return this.http.put<SettingsUpdateResponse>(`${this.baseUrl}/settings`, body);
  }

  getAuthStatus(): Observable<AuthStatusResponse> {
    return this.http.get<AuthStatusResponse>(`${this.baseUrl}/settings/auth`);
  }

  getAuthSettings(): Observable<AuthStatusResponse> {
    return this.getAuthStatus();
  }

  testConnection(body: TestConnectionRequest): Observable<TestConnectionResponse> {
    return this.http.post<TestConnectionResponse>(`${this.baseUrl}/settings/test-connection`, body);
  }

  updateAuth(body: AuthUpdateRequest): Observable<SettingsResponse> {
    return this.http.post<SettingsResponse>(`${this.baseUrl}/settings/auth`, body);
  }

  updateAuthSettings(body: AuthUpdateRequest): Observable<SettingsResponse> {
    return this.updateAuth(body);
  }

  // --- Projects ---
  createProject(body: ProjectCreateRequest): Observable<Project> {
    return this.http.post<Project>(`${this.baseUrl}/projects`, body);
  }

  listProjects(includeArchived?: boolean): Observable<Project[]> {
    let params = '';
    if (includeArchived !== undefined) {
      params = `?include_archived=${includeArchived}`;
    }
    return this.http.get<Project[]>(`${this.baseUrl}/projects${params}`);
  }

  getProject(id: string): Observable<Project> {
    return this.http.get<Project>(`${this.baseUrl}/projects/${id}`);
  }

  updateProject(id: string, body: ProjectUpdateRequest): Observable<Project> {
    return this.http.put<Project>(`${this.baseUrl}/projects/${id}`, body);
  }

  archiveProject(id: string): Observable<{ message: string }> {
    return this.http.patch<{ message: string }>(`${this.baseUrl}/projects/${id}/archive`, {});
  }

  touchProject(id: string): Observable<Project> {
    return this.http.post<Project>(`${this.baseUrl}/projects/${id}/touch`, {});
  }

  openProjectFolder(id: string): Observable<{ message: string, path: string }> {
    return this.http.post<{ message: string, path: string }>(`${this.baseUrl}/projects/${id}/open-folder`, {});
  }

  // --- Research ---
  addQuestion(projectId: string, body: AddQuestionRequest | { text: string } | { question_text: string }): Observable<AddQuestionResponse> {
    const textVal = (body as any).question_text || (body as any).text || '';
    const payload = { question_text: textVal, text: textVal };
    return this.http.post<AddQuestionResponse>(`${this.baseUrl}/research/${projectId}/questions`, payload);
  }

  listQuestions(projectId: string): Observable<ResearchQuestion[]> {
    return this.http.get<{questions: ResearchQuestion[]}>(`${this.baseUrl}/research/${projectId}/questions`).pipe(
      map(res => (res.questions || []).map((q: any) => ({
        id: q.question_id || q.id || String(Date.now()),
        text: q.text || q.question_text || '',
        embedding_status: q.embedding_status || 'embedded',
        coverage_score: q.coverage_score || 0,
        created_at: q.created_at || new Date().toISOString()
      })))
    );
  }

  deleteQuestion(projectId: string, questionId: string): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.baseUrl}/research/${projectId}/questions/${questionId}`);
  }

  getTopAuthors(projectId: string, limit?: number): Observable<{ authors: TopEntity[] }> {
    let url = `${this.baseUrl}/research/${projectId}/top-authors`;
    if (limit !== undefined) {
      url += `?limit=${limit}`;
    }
    return this.http.get<{ authors: TopEntity[] }>(url);
  }

  getTopVenues(projectId: string, limit?: number): Observable<{ venues: TopEntity[] }> {
    let url = `${this.baseUrl}/research/${projectId}/top-venues`;
    if (limit !== undefined) {
      url += `?limit=${limit}`;
    }
    return this.http.get<{ venues: TopEntity[] }>(url);
  }

  searchByAuthor(name: string): Observable<PaperSummary[]> {
    return this.http.get<PaperSummary[]>(`${this.baseUrl}/research/search/author?name=${encodeURIComponent(name)}`);
  }

  searchByVenue(name: string): Observable<PaperSummary[]> {
    return this.http.get<PaperSummary[]>(`${this.baseUrl}/research/search/venue?name=${encodeURIComponent(name)}`);
  }

  // --- Analysis ---
  getPaperSimilarity(projectId: string, doi: string): Observable<QuestionSimilarity[]> {
    return this.http.get<QuestionSimilarity[]>(`${this.baseUrl}/analysis/${projectId}/similarity/${encodeURIComponent(doi)}`);
  }

  getCitationStats(projectId: string): Observable<CitationStats> {
    return this.http.get<CitationStats>(`${this.baseUrl}/analysis/${projectId}/citation-stats`);
  }

  getCoverage(projectId: string, threshold?: number): Observable<CoverageResponse> {
    let url = `${this.baseUrl}/analysis/${projectId}/coverage`;
    if (threshold !== undefined) {
      url += `?threshold=${threshold}`;
    }
    return this.http.get<any>(url).pipe(
      map(res => {
        const coverages: CoverageResult[] = [];
        if (res.gap_questions) {
          coverages.push(...res.gap_questions.map((q: any) => ({
            question_id: q.question_id || '',
            question_text: q.question,
            coverage_score: q.best_score || 0,
            status: 'gap' as const,
            top_papers: [],
            paper_count: q.paper_count || 0
          })));
        }
        if (res.covered_questions) {
          coverages.push(...res.covered_questions.map((q: any) => ({
            question_id: q.question_id || '',
            question_text: q.question,
            coverage_score: q.best_score || 0,
            status: 'covered' as const,
            top_papers: [],
            paper_count: q.paper_count || 0
          })));
        }
        return {
          coverages,
          threshold: threshold || 0.6
        };
      })
    );
  }

  generateGapQueries(projectId: string, body: GapQueryRequest): Observable<GapQueryResponse> {
    return this.http.post<GapQueryResponse>(`${this.baseUrl}/analysis/${projectId}/gap-queries`, body);
  }

  getRankedPapers(projectId: string): Observable<AnalysisRankedPaper[]> {
    return this.http.get<{ranked_papers: AnalysisRankedPaper[]}>(`${this.baseUrl}/analysis/${projectId}/ranked-papers`).pipe(
      map(res => res.ranked_papers || [])
    );
  }

  // --- Planning ---
  getProjectSummary(projectId: string): Observable<ProjectSummary> {
    return this.http.get<ProjectSummary>(`${this.baseUrl}/planning/${projectId}/summary`);
  }

  generateOutline(projectId: string, body: OutlineRequest): Observable<OutlineResponse> {
    return this.http.post<OutlineResponse>(`${this.baseUrl}/planning/${projectId}/outline`, body);
  }

  getOutline(projectId: string): Observable<OutlineResponse> {
    return this.http.get<OutlineResponse>(`${this.baseUrl}/planning/${projectId}/outline`);
  }

  // --- Writing ---
  getAbstracts(projectId: string, body: AbstractsRequest): Observable<AbstractsResponse> {
    return this.http.post<AbstractsResponse>(`${this.baseUrl}/writing/${projectId}/abstracts`, body);
  }

  draftSection(projectId: string, body: DraftRequest): Observable<DraftResponse> {
    return this.http.post<DraftResponse>(`${this.baseUrl}/writing/${projectId}/draft`, body);
  }

  reviewSection(projectId: string, body: ReviewRequest): Observable<ReviewResponse> {
    return this.http.post<ReviewResponse>(`${this.baseUrl}/writing/${projectId}/review`, body);
  }

  // --- Export ---
  exportBibtex(projectId: string): Observable<Blob> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/bibtex`, {}, { responseType: 'blob' });
  }

  exportLatex(projectId: string, body: ExportLatexRequest): Observable<Blob> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/latex`, body, { responseType: 'blob' });
  }

  exportCitationGraph(projectId: string): Observable<Blob> {
    return this.http.post(`${this.baseUrl}/export/${projectId}/citation-graph`, {}, { responseType: 'blob' });
  }

  // --- Papers ---
  getPaperDetail(doi: string): Observable<PaperDetail> {
    return this.http.get<PaperDetail>(`${this.baseUrl}/papers/${encodeURIComponent(doi)}`);
  }

  addPapersToProject(body: AddPapersToProjectRequest): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.baseUrl}/projects/${body.project_id}/papers`, body);
  }

  // --- Logs (Agent Traces) ---
  getAgentTraces(
    projectId?: string,
    agentName?: string,
    since?: string,
    endTime?: string,
    limit: number = 100
  ): Observable<AgentTraceListResponse> {
    let params = `limit=${limit}`;
    if (projectId) params += `&project_id=${encodeURIComponent(projectId)}`;
    if (agentName) params += `&agent_name=${encodeURIComponent(agentName)}`;
    if (since) params += `&since=${encodeURIComponent(since)}`;
    if (endTime) params += `&end_time=${encodeURIComponent(endTime)}`;
    return this.http.get<AgentTraceListResponse>(`${this.baseUrl}/logs/agent-traces?${params}`);
  }

  // --- Project Chats ---
  listProjectChats(projectId: string): Observable<ChatSessionSummary[]> {
    return this.http.get<ChatSessionListResponse>(`${this.baseUrl}/projects/${projectId}/chats`).pipe(
      map(res => res.chats || [])
    );
  }

  createProjectChat(projectId: string, title?: string): Observable<ChatSessionSummary> {
    return this.http.post<ChatSessionSummary>(`${this.baseUrl}/projects/${projectId}/chats`, { title });
  }

  getChatMessages(projectId: string, chatId: string): Observable<ChatMessage[]> {
    return this.http.get<ChatMessagesResponse>(`${this.baseUrl}/projects/${projectId}/chats/${chatId}/messages`).pipe(
      map(res => res.messages || [])
    );
  }

  sendChatMessage(projectId: string, chatId: string, message: string): Observable<SendMessageResponse> {
    return this.http.post<SendMessageResponse>(`${this.baseUrl}/projects/${projectId}/chats/${chatId}/messages`, { message });
  }

  deleteProjectChat(projectId: string, chatId: string): Observable<{ status: string; message: string }> {
    return this.http.delete<{ status: string; message: string }>(`${this.baseUrl}/projects/${projectId}/chats/${chatId}`);
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

// --- Settings & Dual-Mode Auth interfaces ---
export type AuthProviderMode = 'studio' | 'vertex' | 'google_ai_studio' | 'vertex_ai';

export interface AuthStatusResponse {
  mode: AuthProviderMode;
  has_credentials: boolean;
  gemini_api_key_preview?: string | null;
  gemini_api_key_set?: boolean;
  vertex_project?: string | null;
  vertex_location?: string;
  use_vertex_ai: boolean;
  openalex_api_key_preview?: string | null;
  openalex_api_key_set?: boolean;
  openalex_email?: string;
}

export type SettingsAuthResponse = AuthStatusResponse;

export interface TestConnectionRequest {
  mode?: AuthProviderMode;
  gemini_api_key?: string | null;
  vertex_project?: string | null;
  vertex_location?: string | null;
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
  model?: string | null;
  model_name?: string | null;
  latency_ms?: number | null;
  mode?: AuthProviderMode | string | null;
  error?: string | null;
  details?: string | null;
}

export interface AuthUpdateRequest {
  mode?: AuthProviderMode;
  use_vertex_ai?: boolean;
  gemini_api_key?: string | null;
  vertex_project?: string | null;
  vertex_location?: string | null;
  openalex_api_key?: string | null;
  openalex_email?: string;
}

export type SettingsAuthUpdateRequest = AuthUpdateRequest;

export interface SettingsResponse {
  gemini_api_key_set: boolean;
  gemini_api_key_preview: string;
  openalex_api_key_set: boolean;
  openalex_api_key_preview: string;
  openalex_email: string;
  embedding_model: string;
  embedding_dimensions: number;

  // Dual-mode auth extensions
  use_vertex_ai?: boolean;
  mode?: AuthProviderMode;
  vertex_project?: string | null;
  vertex_location?: string;
  has_credentials?: boolean;

  // Tiered Model Architecture
  adk_tier1_model?: string;
  adk_tier2_model?: string;
  available_models?: string[];
}

export interface ModelInfo {
  name: string;
  display_name?: string;
  description?: string;
  supported_actions?: string[];
}

export interface AvailableModelsResponse {
  models: string[];
  model_details: ModelInfo[];
  source: 'google_api' | 'fallback';
  total: number;
}

export interface SettingsUpdateRequest {
  gemini_api_key?: string;
  openalex_api_key?: string;
  openalex_email?: string;
  use_vertex_ai?: boolean;
  vertex_project?: string;
  vertex_location?: string;
  mode?: AuthProviderMode;
  adk_tier1_model?: string;
  adk_tier2_model?: string;
}

export interface SettingsUpdateResponse {
  success: boolean;
  message: string;
  restart_required: boolean;
}

// --- ALRS Project Management Interfaces ---
export interface Project {
  id: string;
  name: string;
  description: string | null;
  topic: string | null;
  target_level: string;
  similarity_threshold: number;
  token_budget: number;
  status: string;
  created_at: string;
  updated_at: string;
  last_accessed_at: string | null;
  paper_count: number;
  question_count: number;

  // Frontend-only computed properties
  is_archived?: boolean;
}

export interface ProjectCreateRequest {
  name: string;
  description?: string;
  topic?: string;
  target_level?: 'master' | 'phd';
}

export interface ProjectUpdateRequest {
  name?: string;
  description?: string;
  topic?: string;
  target_level?: 'master' | 'phd';
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

// --- ALRS Research Interfaces ---
export interface ResearchQuestion {
  id: string;
  text: string;
  embedding_status: 'pending' | 'embedded' | 'failed';
  coverage_score?: number;
  created_at: string;
}

export interface AddQuestionRequest {
  question_text?: string;
  text?: string;
}

export interface AddQuestionResponse {
  question: ResearchQuestion;
  message: string;
}

export interface PaperDetail {
  doi: string;
  title: string;
  abstract: string | null;
  year: number;
  type: string;
  cited_by_count: number;
  authors: Author[];
  venue: Venue | null;
  keywords: string[];
  similarity_scores: QuestionSimilarity[];
}

export interface Author {
  name: string;
  openalex_id: string;
  orcid: string | null;
  affiliations: string[];
}

export interface Venue {
  name: string;
  type: string;
}

export interface QuestionSimilarity {
  question_id: string;
  question_text: string;
  similarity_score: number;
}

export interface TopEntity {
  name: string;
  count: number;
}

// --- ALRS Analysis Interfaces ---
export interface CoverageResult {
  question_id: string;
  question_text: string;
  coverage_score: number;
  status: 'covered' | 'partial' | 'gap';
  top_papers: string[];
  paper_count: number;
}

export interface CoverageResponse {
  coverages: CoverageResult[];
  threshold: number;
}

export interface GapQueryRequest {
  gap_question: string;
  max_queries?: number;
}

export interface GapQueryResponse {
  queries: string[];
  gap_question: string;
}

export interface AnalysisRankedPaper {
  doi: string;
  title: string;
  year: number;
  hybrid_score: number;
  similarity_score: number;
  pagerank_score: number;
  question_similarities: QuestionSimilarity[];
}

export interface CitationStats {
  total_papers: number;
  average_similarity: number;
  network_density: number;
  top_cited: { doi: string; title: string; cited_by_count: number }[];
}

// --- ALRS Planning Interfaces ---
export interface ProjectSummary {
  paper_count: number;
  question_count: number;
  gap_count: number;
  has_outline: boolean;
  has_drafts: boolean;
}

export interface OutlineSection {
  title: string;
  description: string;
  paper_dois: string[];
  order: number;
}

export interface OutlineRequest {
  style?: string;
  num_sections?: number;
}

export interface OutlineResponse {
  sections: OutlineSection[];
  style: string;
}

// --- ALRS Writing Interfaces ---
export interface DraftRequest {
  section_title: string;
  section_description: string;
  paper_dois: string[];
  target_level: 'master' | 'phd';
  outline_context?: string;
}

export interface DraftResponse {
  section_title: string;
  draft_text: string;
  word_count: number;
  citations_used: string[];
}

export interface ReviewRequest {
  section_title: string;
  draft_text: string;
  paper_dois: string[];
  target_level: 'master' | 'phd';
}

export interface ReviewResponse {
  approved: boolean;
  feedback: string[];
  missing_citations: string[];
}

export interface AbstractsRequest {
  dois: string[];
}

export interface AbstractsResponse {
  abstracts: { doi: string; title: string; abstract: string | null }[];
}

// --- ALRS Export Interfaces ---
export interface ExportLatexRequest {
  template: 'ieee' | 'acm' | 'plain';
}

// --- ALRS Agent Trace Interfaces ---
export interface AgentTrace {
  id: string;
  project_id: string;
  agent_name: string;
  action_summary: string;
  tool_calls: ToolCall[];
  llm_prompt?: string;
  llm_response?: string;
  decision_outcome?: string;
  token_count: number;
  timestamp: string;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result: string;
}

export interface AgentTraceListResponse {
  traces: AgentTrace[];
  total: number;
}

// --- ALRS Search Results - Project Import Interfaces ---
export interface AddPapersToProjectRequest {
  project_id: string;
  dois: string[];
}

// --- ALRS Project Chat Interfaces ---
export interface ToolTrace {
  tool_name: string;
  input_args: Record<string, unknown>;
  output_result?: string;
  status: 'success' | 'error' | 'running';
}

export interface CitationTrace {
  doi: string;
  title: string;
  authors: string[];
  year?: number;
  verified_in_graph: boolean;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  sender: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: string;
  tool_traces?: ToolTrace[];
  citations?: CitationTrace[];
}

export interface ChatSessionSummary {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}

export interface ChatSessionListResponse {
  chats: ChatSessionSummary[];
}

export interface ChatMessagesResponse {
  messages: ChatMessage[];
}

export interface SendMessageResponse {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}
