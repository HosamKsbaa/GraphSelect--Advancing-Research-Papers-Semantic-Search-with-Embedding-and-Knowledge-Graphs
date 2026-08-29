import {
  Component,
  EventEmitter,
  Input,
  OnInit,
  Output,
  OnChanges,
  SimpleChanges,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AgentConfigUpdate, AgentMetadata } from '../../../../core/agent.service';
import { ModelTier, TierManagementService } from '../../../../core/tier-management.service';
import { ToolDirectoryComponent } from '../tool-directory/tool-directory.component';
import { MarkdownPreviewComponent } from '../../../../shared/markdown-preview/markdown-preview.component';

@Component({
  selector: 'app-agent-card',
  standalone: true,
  imports: [CommonModule, FormsModule, ToolDirectoryComponent, MarkdownPreviewComponent],
  templateUrl: './agent-card.component.html',
  styleUrl: './agent-card.component.scss',
})
export class AgentCardComponent implements OnInit, OnChanges {
  tierService = inject(TierManagementService);

  @Input({ required: true }) agent!: AgentMetadata;
  @Input() availableModels: string[] = [
    'inherit',
    'gemini-3.7-flash',
    'gemini-3.5-flash-lite',
    'gemini-2.5-pro',
    'gemini-2.5-flash',
  ];
  @Input() draftConfig?: AgentConfigUpdate;
  @Input() isSaving = false;

  @Output() configChange = new EventEmitter<{
    agentName: string;
    config: AgentConfigUpdate;
    update: AgentConfigUpdate;
  }>();
  @Output() resetAgent = new EventEmitter<string>();
  @Output() viewTraces = new EventEmitter<string>();
  @Output() selectAgent = new EventEmitter<AgentMetadata>();

  // Configuration Mode: 'inherit' | 'custom'
  configMode = signal<'inherit' | 'custom'>('inherit');
  assignedTierId = signal<string>('tier1');

  // Local mutable copy of config parameters
  currentModel = 'inherit';
  currentTemperature = 0.7;
  currentTopP = 0.95;
  currentMaxTokens = 8192;
  currentPromptPrefix = '';

  // UI state toggles
  showPromptEditor = signal(false);
  showBasePrompt = signal(false);
  showTools = signal(false);
  hasUnsavedChanges = signal(false);

  // Available Tiers list from TierManagementService
  allTiers = computed(() => this.tierService.tiers());

  // Resolved Current Tier Object
  currentTier = computed(() => {
    return this.tierService.getTierById(this.assignedTierId());
  });

  ngOnInit(): void {
    this.syncFromAgent();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['agent'] || changes['draftConfig']) {
      this.syncFromAgent();
    }
  }

  syncFromAgent(): void {
    if (!this.agent || !this.agent.config) return;

    // 1. Resolve Tier ID
    const tierId =
      this.draftConfig?.assigned_tier_id ||
      this.draftConfig?.tier_id ||
      this.agent.assigned_tier_id ||
      this.agent.config.assigned_tier_id ||
      this.agent.tier ||
      'tier1';
    this.assignedTierId.set(tierId);

    // 2. Resolve Config Mode
    const mode =
      (this.draftConfig?.config_mode as 'inherit' | 'custom') ||
      (this.agent.config_mode as 'inherit' | 'custom') ||
      (this.agent.config.config_mode as 'inherit' | 'custom') ||
      'inherit';
    this.configMode.set(mode);

    // 3. Resolve Parameters based on mode and drafts
    if (this.draftConfig) {
      this.currentModel = this.draftConfig.model ?? this.agent.config.model ?? 'inherit';
      this.currentTemperature = this.draftConfig.temperature ?? this.agent.config.temperature ?? 0.7;
      this.currentTopP = this.draftConfig.top_p ?? this.agent.config.top_p ?? 0.95;
      this.currentMaxTokens = this.draftConfig.max_output_tokens ?? this.agent.config.max_output_tokens ?? 8192;
      this.currentPromptPrefix = this.draftConfig.custom_prompt_prefix ?? '';
    } else {
      if (mode === 'inherit') {
        const tier = this.tierService.getTierById(tierId);
        this.currentModel = tier?.model || this.agent.config.default_model || 'gemini-2.5-flash';
        this.currentTemperature = tier?.temperature ?? this.agent.config.default_temperature ?? 0.7;
        this.currentTopP = tier?.top_p ?? this.agent.config.default_top_p ?? 0.95;
        this.currentMaxTokens = tier?.max_output_tokens ?? this.agent.config.default_max_output_tokens ?? 8192;
      } else {
        this.currentModel = this.agent.config.model || this.agent.config.default_model || 'gemini-2.5-flash';
        this.currentTemperature = this.agent.config.temperature ?? this.agent.config.default_temperature ?? 0.7;
        this.currentTopP = this.agent.config.top_p ?? this.agent.config.default_top_p ?? 0.95;
        this.currentMaxTokens = this.agent.config.max_output_tokens ?? this.agent.config.default_max_output_tokens ?? 8192;
      }
      this.currentPromptPrefix = this.agent.config.custom_prompt_prefix || '';
    }
    this.checkIfModified();
  }

  setMode(mode: 'inherit' | 'custom'): void {
    if (this.configMode() === mode) return;
    this.configMode.set(mode);

    if (mode === 'inherit') {
      const tier = this.currentTier();
      if (tier) {
        this.currentModel = tier.model;
        this.currentTemperature = tier.temperature;
        this.currentTopP = tier.top_p;
        this.currentMaxTokens = tier.max_output_tokens;
      }
    }
    this.emitChange();
  }

  onAssignedTierChange(newTierId: string): void {
    this.assignedTierId.set(newTierId);
    if (this.configMode() === 'inherit') {
      const tier = this.tierService.getTierById(newTierId);
      if (tier) {
        this.currentModel = tier.model;
        this.currentTemperature = tier.temperature;
        this.currentTopP = tier.top_p;
        this.currentMaxTokens = tier.max_output_tokens;
      }
    }
    this.emitChange();
  }

  getAllModels(): string[] {
    const baseList = ['gemini-3.7-flash', 'gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-2.5-pro', 'gemini-2.5-flash'];
    const filteredAvailable = this.availableModels.filter((m) => m !== 'inherit');
    return Array.from(new Set([...baseList, ...filteredAvailable]));
  }

  onModelChange(model: string): void {
    this.currentModel = model;
    this.emitChange();
  }

  onTemperatureChange(temp: number): void {
    this.currentTemperature = Number(temp);
    this.emitChange();
  }

  onTopPChange(topP: number): void {
    this.currentTopP = Number(topP);
    this.emitChange();
  }

  onMaxTokensChange(tokens: number): void {
    this.currentMaxTokens = Number(tokens);
    this.emitChange();
  }

  onPromptPrefixChange(prefix: string): void {
    this.currentPromptPrefix = prefix;
    this.emitChange();
  }

  clearPromptPrefix(): void {
    this.currentPromptPrefix = '';
    this.emitChange();
  }

  emitChange(): void {
    this.checkIfModified();
    const update: AgentConfigUpdate = {
      config_mode: this.configMode(),
      assigned_tier_id: this.assignedTierId(),
      tier_id: this.assignedTierId(),
      model: this.currentModel,
      temperature: this.currentTemperature,
      top_p: this.currentTopP,
      max_output_tokens: this.currentMaxTokens,
      custom_prompt_prefix: this.currentPromptPrefix.trim() || null,
    };
    this.configChange.emit({
      agentName: this.agent.name,
      config: update,
      update: update,
    });
  }

  checkIfModified(): boolean {
    if (!this.agent || !this.agent.config) return false;
    const cfg = this.agent.config;

    const baseMode = this.agent.config_mode || cfg.config_mode || 'inherit';
    const baseTier = this.agent.assigned_tier_id || cfg.assigned_tier_id || this.agent.tier || 'tier1';

    const isMod =
      Boolean(this.draftConfig) ||
      this.configMode() !== baseMode ||
      this.assignedTierId() !== baseTier ||
      (this.configMode() === 'custom' &&
        (this.currentModel !== cfg.default_model ||
          Math.abs(this.currentTemperature - cfg.default_temperature) > 0.001 ||
          Math.abs(this.currentTopP - cfg.default_top_p) > 0.001 ||
          this.currentMaxTokens !== cfg.default_max_output_tokens ||
          Boolean(this.currentPromptPrefix.trim())));

    this.hasUnsavedChanges.set(isMod);
    return isMod;
  }

  onReset(): void {
    this.resetAgent.emit(this.agent.name);
  }

  onViewTraces(): void {
    this.viewTraces.emit(this.agent.name);
  }

  onCardClick(): void {
    this.selectAgent.emit(this.agent);
  }

  getTempBadgeClass(temp: number): string {
    if (temp <= 0.3) return 'temp-deterministic';
    if (temp <= 0.8) return 'temp-balanced';
    return 'temp-creative';
  }

  getTempDescription(temp: number): string {
    if (temp <= 0.3) return 'Deterministic / Exact';
    if (temp <= 0.8) return 'Balanced Reasoning';
    return 'Creative / Diverse';
  }

  formatTokens(tokens: number): string {
    return Number(tokens).toLocaleString() + ' tokens';
  }

  getEffectiveTierColor(): string {
    const tier = this.currentTier();
    return tier?.color || (this.agent.tier === 'tier1' ? '#6366f1' : '#10b981');
  }
}
