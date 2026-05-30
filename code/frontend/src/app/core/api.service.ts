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
}
