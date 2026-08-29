import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { AgentsPage } from './agents.page';
import { AgentRegistryResponse, AgentService } from '../../core/agent.service';
import { ApiService, AvailableModelsResponse } from '../../core/api.service';
import { ToastService } from '../../core/toast.service';
import { TierManagementService, FALLBACK_SYSTEM_TIERS } from '../../core/tier-management.service';

describe('AgentsPage', () => {
  let component: AgentsPage;
  let fixture: ComponentFixture<AgentsPage>;
  let agentServiceMock: any;
  let apiServiceMock: any;
  let toastMock: any;
  let tierServiceMock: any;

  const mockRegistry: AgentRegistryResponse = {
    agents: [
      {
        name: 'ProjectAgent',
        display_name: 'Project Lifecycle Orchestrator',
        description: 'Root orchestrator',
        role: 'Orchestration',
        tier: 'tier1',
        assigned_tier_id: 'tier1',
        config_mode: 'inherit',
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
        assigned_tier_id: 'tier2',
        config_mode: 'inherit',
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
    agentServiceMock = {
      getRegistry: vi.fn().mockReturnValue(of(mockRegistry)),
      updateSettings: vi.fn(),
      resetSettings: vi.fn(),
      getTraces: vi.fn().mockReturnValue(of({ traces: [], total: 0 })),
      testAgentConnection: vi.fn(),
    };

    apiServiceMock = {
      getAvailableModels: vi.fn().mockReturnValue(of(mockModels)),
    };

    toastMock = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    };

    tierServiceMock = {
      tiers: vi.fn().mockReturnValue(FALLBACK_SYSTEM_TIERS),
      editingTier: vi.fn().mockReturnValue(null),
      isEditorOpen: vi.fn().mockReturnValue(false),
      loadTiers: vi.fn().mockReturnValue(of({ tiers: FALLBACK_SYSTEM_TIERS, total: 3 })),
      openEditor: vi.fn(),
      closeEditor: vi.fn(),
      getTierById: vi.fn((id: string) => FALLBACK_SYSTEM_TIERS.find((t) => t.id === id) || FALLBACK_SYSTEM_TIERS[0]),
    };

    await TestBed.configureTestingModule({
      imports: [AgentsPage],
      providers: [
        { provide: AgentService, useValue: agentServiceMock },
        { provide: ApiService, useValue: apiServiceMock },
        { provide: ToastService, useValue: toastMock },
        { provide: TierManagementService, useValue: tierServiceMock },
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

  it('should switch view mode between grid and hierarchy', () => {
    expect(component.viewMode()).toBe('grid');
    component.viewMode.set('hierarchy');
    expect(component.viewMode()).toBe('hierarchy');
  });

  it('should open and close agent drawer', () => {
    expect(component.isDrawerOpen()).toBe(false);
    component.openAgentDrawer(mockRegistry.agents[0]);
    expect(component.isDrawerOpen()).toBe(true);
    expect(component.selectedDrawerAgent()?.name).toBe('ProjectAgent');

    component.closeAgentDrawer();
    expect(component.isDrawerOpen()).toBe(false);
  });

  it('should open tier editor modal', () => {
    component.openTierEditor();
    expect(tierServiceMock.openEditor).toHaveBeenCalled();
  });
});
