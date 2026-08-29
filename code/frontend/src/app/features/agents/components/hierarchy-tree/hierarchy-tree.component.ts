import {
  Component,
  EventEmitter,
  Input,
  Output,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { AgentConfigUpdate, AgentMetadata } from '../../../../core/agent.service';
import { ModelTier, TierManagementService } from '../../../../core/tier-management.service';

export interface TreeNodeData {
  agent: AgentMetadata;
  effectiveModel: string;
  effectiveTemperature: number;
  tier: ModelTier | undefined;
  tierColor: string;
  isModified: boolean;
  hasDraft: boolean;
  children: TreeNodeData[];
}

@Component({
  selector: 'app-hierarchy-tree',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './hierarchy-tree.component.html',
  styleUrl: './hierarchy-tree.component.scss',
})
export class HierarchyTreeComponent {
  tierService = inject(TierManagementService);

  @Input() agents: AgentMetadata[] = [];
  @Input() availableModels: string[] = [];
  @Input() draftUpdates: Map<string, AgentConfigUpdate> = new Map();
  @Input() selectedAgentName?: string;
  @Input() tiers: ModelTier[] = [];

  @Output() agentSelect = new EventEmitter<AgentMetadata>();
  @Output() selectAgent = new EventEmitter<AgentMetadata>();
  @Output() configChange = new EventEmitter<{
    agentName: string;
    config: AgentConfigUpdate;
    update: AgentConfigUpdate;
  }>();
  @Output() resetAgent = new EventEmitter<string>();
  @Output() viewTraces = new EventEmitter<string>();

  // Collapsed branches state: Set of agent names whose sub-branches are collapsed
  collapsedBranches = signal<Set<string>>(new Set());

  // Quick map of agents
  agentMap = computed(() => {
    const map = new Map<string, AgentMetadata>();
    for (const a of this.agents) {
      map.set(a.name, a);
    }
    return map;
  });

  // Root Agent (ProjectAgent)
  rootAgent = computed<AgentMetadata | undefined>(() => {
    return (
      this.agentMap().get('ProjectAgent') ||
      this.agents.find((a) => a.tier === 'tier1' && a.sub_agents.length > 0) ||
      this.agents[0]
    );
  });

  // Coordinator Level 1 Agents
  level1Agents = computed<AgentMetadata[]>(() => {
    const l1Names = ['ResearchAgent', 'PlannerAgent', 'WriterAgent', 'DebuggerAgent'];
    const list: AgentMetadata[] = [];
    for (const name of l1Names) {
      const a = this.agentMap().get(name);
      if (a) list.push(a);
    }
    return list;
  });

  // Children of ResearchAgent
  researchChildren = computed<AgentMetadata[]>(() => {
    const names = ['ALRSAgent', 'GapFinderAgent', 'EvidenceSynthesizerAgent'];
    return names.map((n) => this.agentMap().get(n)).filter(Boolean) as AgentMetadata[];
  });

  // Children of WriterAgent
  writerChildren = computed<AgentMetadata[]>(() => {
    const names = ['DraftingAgent', 'ReviewerAgent'];
    return names.map((n) => this.agentMap().get(n)).filter(Boolean) as AgentMetadata[];
  });

  isBranchCollapsed(agentName: string): boolean {
    return this.collapsedBranches().has(agentName);
  }

  toggleBranch(agentName: string, event?: Event): void {
    if (event) {
      event.stopPropagation();
    }
    const current = new Set(this.collapsedBranches());
    if (current.has(agentName)) {
      current.delete(agentName);
    } else {
      current.add(agentName);
    }
    this.collapsedBranches.set(current);
  }

  expandAll(): void {
    this.collapsedBranches.set(new Set());
  }

  collapseAll(): void {
    this.collapsedBranches.set(new Set(['ResearchAgent', 'WriterAgent']));
  }

  onNodeClick(agent: AgentMetadata): void {
    this.agentSelect.emit(agent);
    this.selectAgent.emit(agent);
  }

  getEffectiveTier(agent: AgentMetadata): ModelTier | undefined {
    const draft = this.draftUpdates.get(agent.name);
    const tierId =
      draft?.assigned_tier_id ||
      draft?.tier_id ||
      agent.assigned_tier_id ||
      agent.config.assigned_tier_id ||
      agent.tier ||
      'tier1';
    return this.tierService.getTierById(tierId);
  }

  getTierColor(agent: AgentMetadata): string {
    const tier = this.getEffectiveTier(agent);
    return tier?.color || (agent.tier === 'tier1' ? '#6366f1' : '#10b981');
  }

  getEffectiveModel(agent: AgentMetadata): string {
    const draft = this.draftUpdates.get(agent.name);
    if (draft?.model) return draft.model;
    const mode = draft?.config_mode || agent.config_mode || agent.config.config_mode || 'inherit';
    if (mode === 'inherit') {
      const tier = this.getEffectiveTier(agent);
      return tier?.model || agent.config.default_model || 'gemini-2.5-flash';
    }
    return agent.config.model || agent.config.default_model || 'gemini-2.5-flash';
  }

  getEffectiveTemperature(agent: AgentMetadata): number {
    const draft = this.draftUpdates.get(agent.name);
    if (draft?.temperature !== undefined) return draft.temperature;
    const mode = draft?.config_mode || agent.config_mode || agent.config.config_mode || 'inherit';
    if (mode === 'inherit') {
      const tier = this.getEffectiveTier(agent);
      return tier?.temperature ?? agent.config.default_temperature ?? 0.7;
    }
    return agent.config.temperature ?? agent.config.default_temperature ?? 0.7;
  }

  isAgentModified(agent: AgentMetadata): boolean {
    const draft = this.draftUpdates.get(agent.name);
    return Boolean(draft) || !agent.config.is_default;
  }

  hasDraftChanges(agent: AgentMetadata): boolean {
    return this.draftUpdates.has(agent.name);
  }

  isSelected(agent: AgentMetadata): boolean {
    return this.selectedAgentName === agent.name;
  }

  getTempBadgeClass(temp: number): string {
    if (temp <= 0.3) return 'temp-deterministic';
    if (temp <= 0.8) return 'temp-balanced';
    return 'temp-creative';
  }
}
