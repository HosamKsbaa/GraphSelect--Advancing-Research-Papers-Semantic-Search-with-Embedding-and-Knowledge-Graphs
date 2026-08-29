import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { AgentsPage } from './agents.page';
import { AgentRegistryResponse, AgentService } from '../../core/agent.service';
import { ApiService, AvailableModelsResponse } from '../../core/api.service';
import { ToastService } from '../../core/toast.service';

describe('AgentsPage', () => {
  let component: AgentsPage;
  let fixture: ComponentFixture<AgentsPage>;
  let agentServiceSpy: jasmine.SpyObj<AgentService>;
  let apiServiceSpy: jasmine.SpyObj<ApiService>;
  let toastSpy: jasmine.SpyObj<ToastService>;

  const mockRegistry: AgentRegistryResponse = {
    agents: [
      {
        name: 'ProjectAgent',
        display_name: 'Project Lifecycle Orchestrator',
        description: 'Root orchestrator',
        role: 'Orchestration',
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
          system_prompt: 'Instructions...',
          is_default: true,
        },
      },
      {
        name: 'ALRSAgent',
        display_name: 'Literature Discovery Specialist',
        description: 'Discovery node',
        role: 'Search & Discovery',
        tier: 'tier2',
        sub_agents: [],
        tools: [],
        config: {
          model: 'gemini-3.5-flash-lite',
          default_model: 'gemini-3.5-flash-lite',
          temperature: 0.2,
          default_temperature: 0.2,
          top_p: 0.95,
          default_top_p: 0.95,
          max_output_tokens: 8192,
          default_max_output_tokens: 8192,
          custom_prompt_prefix: null,
          system_prompt: 'Instructions...',
          is_default: true,
        },
      },
    ],
    total: 2,
    system_default_tier1_model: 'gemini-2.5-flash',
    system_default_tier2_model: 'gemini-3.5-flash-lite',
  };

  const mockModels: AvailableModelsResponse = {
    models: ['gemini-3.7-flash', 'gemini-2.5-flash', 'gemini-3.5-flash-lite'],
    model_details: [],
    source: 'google_api',
    total: 3,
  };

  beforeEach(async () => {
    agentServiceSpy = jasmine.createSpyObj('AgentService', [
      'getRegistry',
      'updateSettings',
      'resetSettings',
      'getTraces',
      'testAgentConnection',
    ]);
    apiServiceSpy = jasmine.createSpyObj('ApiService', ['getAvailableModels']);
    toastSpy = jasmine.createSpyObj('ToastService', ['success', 'error', 'info', 'warning']);

    agentServiceSpy.getRegistry.and.returnValue(of(mockRegistry));
    agentServiceSpy.getTraces.and.returnValue(of({ traces: [], total: 0 }));
    apiServiceSpy.getAvailableModels.and.returnValue(of(mockModels));

    await TestBed.configureTestingModule({
      imports: [AgentsPage],
      providers: [
        { provide: AgentService, useValue: agentServiceSpy },
        { provide: ApiService, useValue: apiServiceSpy },
        { provide: ToastService, useValue: toastSpy },
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AgentsPage);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create the page and load agents from registry', () => {
    expect(component).toBeTruthy();
    expect(component.agents().length).toBe(2);
    expect(component.totalAgents()).toBe(2);
  });

  it('should filter agents by tier', () => {
    component.tierFilter.set('tier1');
    fixture.detectChanges();
    expect(component.filteredAgents().length).toBe(1);
    expect(component.filteredAgents()[0].name).toBe('ProjectAgent');

    component.tierFilter.set('tier2');
    fixture.detectChanges();
    expect(component.filteredAgents().length).toBe(1);
    expect(component.filteredAgents()[0].name).toBe('ALRSAgent');
  });

  it('should filter agents by search query', () => {
    component.searchQuery.set('discovery');
    fixture.detectChanges();
    expect(component.filteredAgents().length).toBe(1);
    expect(component.filteredAgents()[0].name).toBe('ALRSAgent');
  });

  it('should track draft updates when agent configuration is changed', () => {
    component.onAgentConfigChange({
      agentName: 'ALRSAgent',
      config: { temperature: 0.5 },
    });
    expect(component.unsavedChangesCount()).toBe(1);
    expect(component.getDraftForAgent('ALRSAgent')?.temperature).toBe(0.5);
  });

  it('should switch tabs between swarm and traces', () => {
    expect(component.activeTab()).toBe('swarm');
    component.activeTab.set('traces');
    expect(component.activeTab()).toBe('traces');
  });
});
