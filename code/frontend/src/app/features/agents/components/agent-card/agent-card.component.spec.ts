import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { AgentCardComponent } from './agent-card.component';
import { AgentMetadata } from '../../../../core/agent.service';
import { TierManagementService, FALLBACK_SYSTEM_TIERS } from '../../../../core/tier-management.service';

describe('AgentCardComponent', () => {
  let component: AgentCardComponent;
  let fixture: ComponentFixture<AgentCardComponent>;

  const mockAgent: AgentMetadata = {
    name: 'ALRSAgent',
    display_name: 'Literature Discovery Specialist',
    description: 'Executes OpenAlex API & BFS citation traversal',
    role: 'Search & Discovery Specialist',
    tier: 'tier2',
    assigned_tier_id: 'tier2',
    config_mode: 'inherit',
    sub_agents: [],
    tools: [],
    config: {
      config_mode: 'inherit',
      assigned_tier_id: 'tier2',
      model: 'gemini-3.5-flash-lite',
      default_model: 'gemini-3.5-flash-lite',
      temperature: 0.2,
      default_temperature: 0.2,
      top_p: 0.95,
      default_top_p: 0.95,
      max_output_tokens: 8192,
      default_max_output_tokens: 8192,
      custom_prompt_prefix: null,
      system_prompt: 'You are ALRSAgent...',
      is_default: true,
      effective_model: 'gemini-3.5-flash-lite',
      effective_temperature: 0.2,
      effective_top_p: 0.95,
      effective_max_output_tokens: 8192,
    },
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AgentCardComponent],
      providers: [
        TierManagementService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AgentCardComponent);
    component = fixture.componentInstance;
    component.agent = mockAgent;
    fixture.detectChanges();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize config from agent inputs in inherit mode', () => {
    expect(component.configMode()).toBe('inherit');
    expect(component.assignedTierId()).toBe('tier2');
    expect(component.currentModel).toBe('gemini-3.5-flash-lite');
    expect(component.currentTemperature).toBe(0.2);
    expect(component.currentTopP).toBe(0.95);
    expect(component.currentMaxTokens).toBe(8192);
  });

  it('should toggle configuration mode to custom and emit update event', () => {
    let emittedEvent: any = null;
    component.configChange.subscribe((event) => {
      emittedEvent = event;
    });

    component.setMode('custom');
    expect(component.configMode()).toBe('custom');
    expect(emittedEvent).toBeTruthy();
    expect(emittedEvent.config.config_mode).toBe('custom');
  });

  it('should switch assigned tier and cascade tier parameters in inherit mode', () => {
    let emittedEvent: any = null;
    component.configChange.subscribe((event) => {
      emittedEvent = event;
    });

    component.onAssignedTierChange('tier1');
    expect(component.assignedTierId()).toBe('tier1');
    expect(component.currentModel).toBe('gemini-2.5-flash');
    expect(component.currentTemperature).toBe(0.7);
    expect(emittedEvent).toBeTruthy();
    expect(emittedEvent.config.assigned_tier_id).toBe('tier1');
  });

  it('should detect when temperature is modified in custom mode and emit update event', () => {
    component.setMode('custom');
    let emittedEvent: any = null;
    component.configChange.subscribe((event) => {
      emittedEvent = event;
    });

    component.onTemperatureChange(0.85);

    expect(component.currentTemperature).toBe(0.85);
    expect(component.hasUnsavedChanges()).toBe(true);
    expect(emittedEvent).toBeTruthy();
    expect(emittedEvent.agentName).toBe('ALRSAgent');
    expect(emittedEvent.config.temperature).toBe(0.85);
  });

  it('should format token badges correctly', () => {
    expect(component.formatTokens(8192)).toBe('8,192 tokens');
    expect(component.formatTokens(65536)).toBe('65,536 tokens');
  });

  it('should assign correct temperature badge classes', () => {
    expect(component.getTempBadgeClass(0.2)).toBe('temp-deterministic');
    expect(component.getTempBadgeClass(0.7)).toBe('temp-balanced');
    expect(component.getTempBadgeClass(1.5)).toBe('temp-creative');
  });
});
