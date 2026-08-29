import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { AgentDrawerComponent } from './agent-drawer.component';
import { AgentMetadata } from '../../../../core/agent.service';
import { TierManagementService } from '../../../../core/tier-management.service';

describe('AgentDrawerComponent', () => {
  let component: AgentDrawerComponent;
  let fixture: ComponentFixture<AgentDrawerComponent>;

  const mockAgent: AgentMetadata = {
    name: 'ResearchAgent',
    display_name: 'Research Swarm Coordinator',
    description: 'Coordinates discovery and literature analysis',
    role: 'Coordinator',
    tier: 'tier1',
    assigned_tier_id: 'tier1',
    config_mode: 'inherit',
    sub_agents: ['ALRSAgent'],
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
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AgentDrawerComponent],
      providers: [
        TierManagementService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AgentDrawerComponent);
    component = fixture.componentInstance;
    component.agent = mockAgent;
    component.isOpen = true;
    fixture.detectChanges();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  it('should emit close event when onClose is called', () => {
    let closed = false;
    component.close.subscribe(() => {
      closed = true;
    });

    component.onClose();
    expect(closed).toBe(true);
  });

  it('should forward config changes and save events', () => {
    let emittedUpdate: any = null;
    component.configChange.subscribe((ev) => {
      emittedUpdate = ev;
    });

    component.onConfigChange({
      agentName: 'ResearchAgent',
      config: { temperature: 0.9 },
      update: { temperature: 0.9 },
    });

    expect(emittedUpdate).toBeTruthy();
    expect(emittedUpdate.config.temperature).toBe(0.9);

    let savedAgent: string | null = null;
    component.saveAgent.subscribe((name) => {
      savedAgent = name;
    });

    component.onSaveClick();
    expect(savedAgent).toBe('ResearchAgent');
  });
});
