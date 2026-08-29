import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ApiService, TestConnectionResponse } from './api.service';

export interface ToolParameterProperty {
  type: string;
  description?: string;
  enum?: string[];
  items?: Record<string, unknown>;
  default?: unknown;
}

export interface ToolParameterSchema {
  type: string;
  properties: Record<string, ToolParameterProperty | any>;
  required?: string[];
}

export interface AgentToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameterSchema;
}

export interface AgentConfig {
  model: string;
  default_model: string;
  temperature: number;
  default_temperature: number;
  top_p: number;
  default_top_p: number;
  max_output_tokens: number;
  default_max_output_tokens: number;
  custom_prompt_prefix: string | null;
  system_prompt: string;
  is_default: boolean;
}

export interface AgentMetadata {
  name: string;
  display_name: string;
  description: string;
  role: string;
  tier: 'tier1' | 'tier2' | string;
  sub_agents: string[];
  tools: AgentToolDefinition[];
  config: AgentConfig;
}

export interface AgentRegistryResponse {
  agents: AgentMetadata[];
  total: number;
  system_default_tier1_model: string;
  system_default_tier2_model: string;
}

export interface AgentConfigUpdate {
  model?: string;
  temperature?: number;
  top_p?: number;
  max_output_tokens?: number;
  custom_prompt_prefix?: string | null;
}

export interface AgentSettingsUpdateRequest {
  settings: Record<string, AgentConfigUpdate>;
}

export interface AgentSettingsUpdateResponse {
  success: boolean;
  message: string;
  updated_agents: string[];
}

export interface AgentResetRequest {
  agent_name?: string;
}

export interface AgentResetResponse {
  success: boolean;
  message: string;
  reset_agents: string[];
}

export interface ToolCallTrace {
  name: string;
  arguments: Record<string, unknown>;
  result: string;
}

export interface LiveAgentTrace {
  id: string;
  timestamp: string;
  project_id?: string | null;
  agent_name: string;
  action_summary: string;
  llm_prompt?: string | null;
  llm_response?: string | null;
  tool_calls: ToolCallTrace[];
  token_count: number;
  latency_ms?: number | null;
  status: 'success' | 'error' | string;
  decision_outcome?: string | null;
}

export interface AgentTraceListResponse {
  traces: LiveAgentTrace[];
  total: number;
}

export interface AgentTraceFilters {
  agent_name?: string;
  project_id?: string;
  since?: string;
  limit?: number;
}

@Injectable({ providedIn: 'root' })
export class AgentService {
  private http = inject(HttpClient);
  private api = inject(ApiService);

  private get baseUrl(): string {
    return this.api.baseUrl;
  }

  getRegistry(): Observable<AgentRegistryResponse> {
    return this.http.get<AgentRegistryResponse>(`${this.baseUrl}/agents/registry`);
  }

  updateSettings(request: AgentSettingsUpdateRequest): Observable<AgentSettingsUpdateResponse> {
    return this.http.put<AgentSettingsUpdateResponse>(`${this.baseUrl}/agents/settings`, request);
  }

  resetSettings(agentName?: string): Observable<AgentResetResponse> {
    const payload: AgentResetRequest = agentName ? { agent_name: agentName } : {};
    return this.http.post<AgentResetResponse>(`${this.baseUrl}/agents/settings/reset`, payload);
  }

  getTraces(filters?: AgentTraceFilters): Observable<AgentTraceListResponse> {
    let params = `limit=${filters?.limit || 100}`;
    if (filters?.agent_name) {
      params += `&agent_name=${encodeURIComponent(filters.agent_name)}`;
    }
    if (filters?.project_id) {
      params += `&project_id=${encodeURIComponent(filters.project_id)}`;
    }
    if (filters?.since) {
      params += `&since=${encodeURIComponent(filters.since)}`;
    }
    return this.http.get<AgentTraceListResponse>(`${this.baseUrl}/agents/traces?${params}`);
  }

  testAgentConnection(agentName?: string, model?: string): Observable<TestConnectionResponse> {
    return this.http.post<TestConnectionResponse>(`${this.baseUrl}/settings/test-connection`, {
      mode: 'studio',
      model_name: model || undefined,
    });
  }
}
