import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { HierarchyTreeComponent } from './hierarchy-tree.component';
import { AgentMetadata } from '../../../../core/agent.service';
import { TierManagementService } from '../../../../core/tier-management.service';

describe('HierarchyTreeComponent', () => {
  let component: HierarchyTreeComponent;
  let fixture: ComponentFixture<HierarchyTreeComponent>;

  const mockAgents: AgentMetadata[] = [
    {
      name: 'ProjectAgent',
      display_name: 'Project Lifecycle Orchestrator',
      description: 'Root orchestrator',
      role: 'Orchestrator',
      tier: 'tier1',
      assigned_tier_id: 'tier1',
      config_mode: 'inherit',
      sub_agents: ['ResearchAgent', 'PlannerAgent', 'WriterAgent', 'DebuggerAgent'],
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'ResearchAgent',
      display_name: 'Research Swarm Coordinator',
      description: 'Coordinates research',
      role: 'Coordinator',
      tier: 'tier1',
      assigned_tier_id: 'tier1',
      config_mode: 'inherit',
      sub_agents: ['ALRSAgent', 'GapFinderAgent', 'EvidenceSynthesizerAgent'],
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'ALRSAgent',
      display_name: 'Literature Discovery Specialist',
      description: 'Executes OpenAlex traversal',
      role: 'Discovery',
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'GapFinderAgent',
      display_name: 'Research Gap Analyst',
      description: 'Analyzes research gaps',
      role: 'Gap Analysis',
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'EvidenceSynthesizerAgent',
      display_name: 'Evidence Matrix Synthesizer',
      description: 'Synthesizes literature matrix',
      role: 'Synthesis',
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'PlannerAgent',
      display_name: 'Paper Outline Planner',
      description: 'Generates outlines',
      role: 'Planning',
      tier: 'tier1',
      assigned_tier_id: 'tier1',
      config_mode: 'inherit',
      sub_agents: [],
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'WriterAgent',
      display_name: 'Writing Loop Coordinator',
      description: 'Coordinates writing loop',
      role: 'Writing',
      tier: 'tier1',
      assigned_tier_id: 'tier1',
      config_mode: 'inherit',
      sub_agents: ['DraftingAgent', 'ReviewerAgent'],
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'DraftingAgent',
      display_name: 'Section Drafting Specialist',
      description: 'Drafts sections',
      role: 'Drafting',
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'ReviewerAgent',
      display_name: 'Peer Review & Critique Specialist',
      description: 'Critiques text',
      role: 'Reviewer',
      tier: 'tier1',
      assigned_tier_id: 'tier1',
      config_mode: 'inherit',
      sub_agents: [],
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
        system_prompt: '...',
        is_default: true,
      },
    },
    {
      name: 'DebuggerAgent',
      display_name: 'Autonomous Diagnostic Repair Agent',
      description: 'Diagnoses issues',
      role: 'Diagnostics',
      tier: 'tier1',
      assigned_tier_id: 'tier1',
      config_mode: 'inherit',
      sub_agents: [],
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
        system_prompt: '...',
        is_default: true,
      },
    },
  ];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HierarchyTreeComponent],
      providers: [
        TierManagementService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(HierarchyTreeComponent);
    component = fixture.componentInstance;
    component.agents = mockAgents;
    fixture.detectChanges();
  });

  it('should create the component and resolve root node', () => {
    expect(component).toBeTruthy();
    expect(component.rootAgent()?.name).toBe('ProjectAgent');
    expect(component.level1Agents().length).toBe(4);
  });

  it('should render root, coordinator, and worker nodes in the DOM', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.root-node')).toBeTruthy();
    expect(compiled.querySelectorAll('.coord-node').length).toBeGreaterThanOrEqual(4);
    expect(compiled.querySelectorAll('.worker-node').length).toBeGreaterThanOrEqual(4);
  });

  it('should toggle collapse and expand branches', () => {
    expect(component.isBranchCollapsed('ResearchAgent')).toBe(false);

    component.toggleBranch('ResearchAgent');
    expect(component.isBranchCollapsed('ResearchAgent')).toBe(true);

    component.expandAll();
    expect(component.isBranchCollapsed('ResearchAgent')).toBe(false);

    component.collapseAll();
    expect(component.isBranchCollapsed('ResearchAgent')).toBe(true);
    expect(component.isBranchCollapsed('WriterAgent')).toBe(true);
  });

  it('should emit agentSelect when a node is clicked', () => {
    let selected: AgentMetadata | null = null;
    component.agentSelect.subscribe((agent) => {
      selected = agent;
    });

    component.onNodeClick(mockAgents[2]); // ALRSAgent
    expect(selected).toBeTruthy();
    expect((selected as any)?.name).toBe('ALRSAgent');
  });

  it('should format temperature and token badges properly', () => {
    expect(component.getTempBadgeClass(0.2)).toBe('temp-deterministic');
    expect(component.getTempBadgeClass(0.7)).toBe('temp-balanced');
    expect(component.getTempBadgeClass(1.5)).toBe('temp-creative');
  });
});
