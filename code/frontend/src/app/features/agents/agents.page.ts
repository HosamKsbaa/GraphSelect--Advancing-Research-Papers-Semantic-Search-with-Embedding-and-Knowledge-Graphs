import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  AgentConfigUpdate,
  AgentMetadata,
  AgentRegistryResponse,
  AgentService,
  AgentSettingsUpdateRequest,
} from '../../core/agent.service';
import { ApiService, AvailableModelsResponse } from '../../core/api.service';
import { ToastService } from '../../core/toast.service';
import {
  ModelTier,
  TierManagementService,
} from '../../core/tier-management.service';
import { AgentCardComponent } from './components/agent-card/agent-card.component';
import { HierarchyTreeComponent } from './components/hierarchy-tree/hierarchy-tree.component';
import { TierEditorModalComponent } from './components/tier-editor-modal/tier-editor-modal.component';
import { AgentDrawerComponent } from './components/agent-drawer/agent-drawer.component';
import { TraceViewerComponent } from './components/trace-viewer/trace-viewer.component';

@Component({
  selector: 'alrs-agents-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    AgentCardComponent,
    HierarchyTreeComponent,
    TierEditorModalComponent,
    AgentDrawerComponent,
    TraceViewerComponent,
  ],
  templateUrl: './agents.page.html',
  styleUrl: './agents.page.scss',
})
export class AgentsPage implements OnInit {
  agentService = inject(AgentService);
  tierService = inject(TierManagementService);
  apiService = inject(ApiService);
  toast = inject(ToastService);

  // Active Tab & View Mode
  activeTab = signal<'swarm' | 'traces'>('swarm');
  viewMode = signal<'grid' | 'hierarchy'>('grid');

  // Loading States
  loading = signal<boolean>(true);
  saving = signal<boolean>(false);
  resettingAll = signal<boolean>(false);
  testingConnection = signal<boolean>(false);

  // Registry Data
  registry = signal<AgentRegistryResponse | null>(null);
  agents = signal<AgentMetadata[]>([]);
  availableModels = signal<string[]>([
    'inherit',
    'gemini-3.7-flash',
    'gemini-3.5-flash',
    'gemini-3.5-flash-lite',
    'gemini-2.5-pro',
    'gemini-2.5-flash',
  ]);

  // Working Draft Edits (Map of agentName -> AgentConfigUpdate)
  draftUpdates = signal<Map<string, AgentConfigUpdate>>(new Map());

  // Search & Filter
  searchQuery = signal<string>('');
  tierFilter = signal<string>('all');
  statusFilter = signal<'all' | 'modified' | 'default'>('all');

  // Trace viewer pre-filter
  selectedTraceAgent = signal<string | undefined>(undefined);

  // Agent Drawer State
  selectedDrawerAgent = signal<AgentMetadata | null>(null);
  isDrawerOpen = signal<boolean>(false);

  // Computed Metrics & Lists
  totalAgents = computed(() => this.agents().length);
  
  totalToolsCount = computed(() =>
    this.agents().reduce((sum, agent) => sum + (agent.tools?.length || 0), 0)
  );

  modifiedCount = computed(() => {
    const drafts = this.draftUpdates();
    let count = 0;
    for (const agent of this.agents()) {
      const draft = drafts.get(agent.name);
      if (draft) {
        count++;
      } else if (!agent.config.is_default) {
        count++;
      }
    }
    return count;
  });

  unsavedChangesCount = computed(() => this.draftUpdates().size);

  filteredAgents = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const tier = this.tierFilter();
    const status = this.statusFilter();
    const drafts = this.draftUpdates();

    return this.agents().filter(agent => {
      // Tier filter
      if (tier !== 'all') {
        const agentTierId =
          agent.assigned_tier_id ||
          agent.config?.assigned_tier_id ||
          agent.tier;
        if (agentTierId !== tier && agent.tier !== tier) return false;
      }

      // Status filter
      const isDrafted = drafts.has(agent.name);
      const isModified = isDrafted || !agent.config.is_default;
      if (status === 'modified' && !isModified) return false;
      if (status === 'default' && isModified) return false;

      // Query filter
      if (q) {
        const matchName = agent.name.toLowerCase().includes(q);
        const matchDisplay = agent.display_name.toLowerCase().includes(q);
        const matchDesc = agent.description.toLowerCase().includes(q);
        const matchRole = agent.role.toLowerCase().includes(q);
        const matchTool = agent.tools?.some(t => t.name.toLowerCase().includes(q));
        if (!matchName && !matchDisplay && !matchDesc && !matchRole && !matchTool) {
          return false;
        }
      }

      return true;
    });
  });

  tier1Agents = computed(() =>
    this.filteredAgents().filter(a => (a.assigned_tier_id || a.tier) === 'tier1')
  );

  tier2Agents = computed(() =>
    this.filteredAgents().filter(a => (a.assigned_tier_id || a.tier) === 'tier2')
  );

  allAgentNames = computed(() => this.agents().map(a => a.name));

  ngOnInit(): void {
    this.loadRegistry();
    this.loadModels();
    this.loadTiers();
  }

  loadRegistry(): void {
    this.loading.set(true);
    this.agentService.getRegistry().subscribe({
      next: (res) => {
        this.registry.set(res);
        this.agents.set(res.agents);
        this.loading.set(false);
        // If drawer is open, keep selected drawer agent synced
        if (this.selectedDrawerAgent()) {
          const updated = res.agents.find(a => a.name === this.selectedDrawerAgent()!.name);
          if (updated) {
            this.selectedDrawerAgent.set(updated);
          }
        }
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.error(
          'Agent Registry Load Failed',
          err.error?.detail || 'Could not introspect live ADK agents.'
        );
      },
    });
  }

  loadModels(): void {
    this.apiService.getAvailableModels().subscribe({
      next: (res: AvailableModelsResponse) => {
        if (res.models && res.models.length > 0) {
          const list = ['inherit', ...res.models.filter(m => m !== 'inherit')];
          this.availableModels.set(list);
        }
      },
      error: () => {
        // Fallback default list remains active
      },
    });
  }

  loadTiers(): void {
    this.tierService.loadTiers().subscribe({
      next: () => {
        // Tiers loaded into signal
      },
      error: () => {
        // Fallback default tiers already active
      },
    });
  }

  openTierEditor(tier?: ModelTier): void {
    this.tierService.openEditor(tier);
  }

  closeTierEditor(): void {
    this.tierService.closeEditor();
  }

  onTierUpdated(tier: ModelTier): void {
    this.loadRegistry();
  }

  onTierCreated(tier: ModelTier): void {
    this.loadRegistry();
  }

  onTierDeleted(tierId: string): void {
    this.loadRegistry();
  }

  openAgentDrawer(agent: AgentMetadata): void {
    this.selectedDrawerAgent.set(agent);
    this.isDrawerOpen.set(true);
  }

  closeAgentDrawer(): void {
    this.isDrawerOpen.set(false);
  }

  onAgentConfigChange(event: { agentName: string; config?: AgentConfigUpdate; update?: AgentConfigUpdate }): void {
    const updatePayload = event.config || event.update;
    if (!updatePayload) return;
    const map = new Map(this.draftUpdates());
    map.set(event.agentName, updatePayload);
    this.draftUpdates.set(map);
  }

  saveSingleAgent(agentName: string): void {
    const draft = this.draftUpdates().get(agentName);
    if (!draft) {
      this.toast.info('No Changes', `No unsaved changes for ${agentName}.`);
      return;
    }

    this.saving.set(true);
    const request: AgentSettingsUpdateRequest = {
      settings: { [agentName]: draft },
    };

    this.agentService.updateSettings(request).subscribe({
      next: () => {
        this.saving.set(false);
        this.toast.success(
          'Agent Settings Saved',
          `Successfully saved and hot-reloaded configuration for ${agentName}.`
        );
        const map = new Map(this.draftUpdates());
        map.delete(agentName);
        this.draftUpdates.set(map);
        this.loadRegistry();
      },
      error: (err) => {
        this.saving.set(false);
        this.toast.error(
          'Save Failed',
          err.error?.detail || `Could not save configuration for ${agentName}.`
        );
      },
    });
  }

  saveAllSettings(): void {
    const drafts = this.draftUpdates();
    if (drafts.size === 0) {
      this.toast.info('No Changes', 'All agent configurations are up to date.');
      return;
    }

    this.saving.set(true);
    const settingsPayload: Record<string, AgentConfigUpdate> = {};
    drafts.forEach((update, agentName) => {
      settingsPayload[agentName] = update;
    });

    const request: AgentSettingsUpdateRequest = { settings: settingsPayload };

    this.agentService.updateSettings(request).subscribe({
      next: (res) => {
        this.saving.set(false);
        this.toast.success(
          'Swarm Settings Saved & Hot-Reloaded',
          `Successfully updated ${res.updated_agents.length} agent(s). Changes applied instantly to runtime instances.`
        );
        this.draftUpdates.set(new Map());
        this.loadRegistry();
      },
      error: (err) => {
        this.saving.set(false);
        this.toast.error(
          'Save Failed',
          err.error?.detail || 'Could not persist agent configurations.'
        );
      },
    });
  }

  resetAgent(agentName: string): void {
    this.agentService.resetSettings(agentName).subscribe({
      next: () => {
        this.toast.success(
          'Agent Reset to Default',
          `Restored factory defaults for ${agentName}.`
        );
        const map = new Map(this.draftUpdates());
        map.delete(agentName);
        this.draftUpdates.set(map);
        this.loadRegistry();
      },
      error: (err) => {
        this.toast.error(
          'Reset Failed',
          err.error?.detail || `Could not reset ${agentName}.`
        );
      },
    });
  }

  resetAllToDefaults(): void {
    if (!confirm('Are you sure you want to reset ALL 9 swarm agents to canonical system factory defaults? Any custom prompt overrides and tuned parameters will be restored.')) {
      return;
    }

    this.resettingAll.set(true);
    this.agentService.resetSettings().subscribe({
      next: (res) => {
        this.resettingAll.set(false);
        this.toast.success(
          'All Agents Reset',
          `Successfully restored factory defaults for all ${res.reset_agents.length} agents.`
        );
        this.draftUpdates.set(new Map());
        this.loadRegistry();
      },
      error: (err) => {
        this.resettingAll.set(false);
        this.toast.error(
          'Reset All Failed',
          err.error?.detail || 'Could not reset swarm to defaults.'
        );
      },
    });
  }

  testConnection(): void {
    this.testingConnection.set(true);
    this.agentService.testAgentConnection().subscribe({
      next: (res) => {
        this.testingConnection.set(false);
        if (res.success) {
          const lat = res.latency_ms ? ` (${res.latency_ms}ms)` : '';
          this.toast.success('Agent Connection Verified', `Google Gemini API responsive${lat}.`);
        } else {
          this.toast.error('Connection Test Failed', res.error || res.message || 'API connection failed.');
        }
      },
      error: (err) => {
        this.testingConnection.set(false);
        this.toast.error('Connection Test Error', err.error?.detail || err.message || 'Network error.');
      },
    });
  }

  navigateToTraces(agentName?: string): void {
    this.selectedTraceAgent.set(agentName);
    this.activeTab.set('traces');
  }

  getDraftForAgent(agentName: string): AgentConfigUpdate | undefined {
    return this.draftUpdates().get(agentName);
  }
}
