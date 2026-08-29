import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import {
  AgentService,
  AgentRegistryResponse,
  AgentSettingsUpdateRequest,
  AgentSettingsUpdateResponse,
  AgentResetResponse,
  AgentTraceListResponse,
} from './agent.service';
import { ApiService } from './api.service';

describe('AgentService', () => {
  let service: AgentService;
  let httpMock: HttpTestingController;
  let apiService: ApiService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        AgentService,
        ApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(AgentService);
    httpMock = TestBed.inject(HttpTestingController);
    apiService = TestBed.inject(ApiService);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should fetch agent registry', () => {
    const mockResponse: AgentRegistryResponse = {
      agents: [
        {
          name: 'ProjectAgent',
          display_name: 'Project Lifecycle Orchestrator',
          description: 'Root coordinator',
          role: 'Orchestrator',
          tier: 'tier1',
          sub_agents: ['ResearchAgent'],
          tools: [],
          config: {
            model: 'gemini-2.5-flash',
            default_model: 'gemini-2.5-flash',
            temperature: 0.7,
            default_temperature: 0.7,
            top_p: 0.95,
            default_top_p: 0.95,
            max_output_tokens: 8192,
            default_max_output_tokens: 8192,
            custom_prompt_prefix: null,
            system_prompt: 'System prompt instructions',
            is_default: true,
          },
        },
      ],
      total: 1,
      system_default_tier1_model: 'gemini-2.5-flash',
      system_default_tier2_model: 'gemini-3.5-flash-lite',
    };

    service.getRegistry().subscribe((res) => {
      expect(res.agents.length).toBe(1);
      expect(res.agents[0].name).toBe('ProjectAgent');
    });

    const req = httpMock.expectOne(`${apiService.baseUrl}/agents/registry`);
    expect(req.request.method).toBe('GET');
    req.flush(mockResponse);
  });

  it('should update agent settings via PUT', () => {
    const updateReq: AgentSettingsUpdateRequest = {
      settings: {
        ALRSAgent: {
          temperature: 0.2,
          max_output_tokens: 4096,
        },
      },
    };

    const mockResponse: AgentSettingsUpdateResponse = {
      success: true,
      message: 'Updated ALRSAgent',
      updated_agents: ['ALRSAgent'],
    };

    service.updateSettings(updateReq).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.updated_agents).toContain('ALRSAgent');
    });

    const req = httpMock.expectOne(`${apiService.baseUrl}/agents/settings`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual(updateReq);
    req.flush(mockResponse);
  });

  it('should reset agent settings via POST', () => {
    const mockResponse: AgentResetResponse = {
      success: true,
      message: 'Reset complete',
      reset_agents: ['ProjectAgent', 'ALRSAgent'],
    };

    service.resetSettings().subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.reset_agents.length).toBe(2);
    });

    const req = httpMock.expectOne(`${apiService.baseUrl}/agents/settings/reset`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush(mockResponse);
  });

  it('should get traces with filter query params', () => {
    const mockTracesResponse: AgentTraceListResponse = {
      traces: [
        {
          id: 'trace-1',
          timestamp: '2026-08-29T12:00:00Z',
          agent_name: 'ALRSAgent',
          action_summary: 'Executed 1-hop traversal',
          tool_calls: [],
          token_count: 500,
          status: 'success',
        },
      ],
      total: 1,
    };

    service.getTraces({ agent_name: 'ALRSAgent', limit: 50 }).subscribe((res) => {
      expect(res.traces.length).toBe(1);
      expect(res.traces[0].agent_name).toBe('ALRSAgent');
    });

    const req = httpMock.expectOne(
      (r) => r.url === `${apiService.baseUrl}/agents/traces` && r.params.get('agent_name') === 'ALRSAgent'
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockTracesResponse);
  });
});
