import { Component, EventEmitter, Input, OnInit, Output, OnChanges, SimpleChanges, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AgentConfigUpdate, AgentMetadata } from '../../../../core/agent.service';
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

  @Output() configChange = new EventEmitter<{ agentName: string; config: AgentConfigUpdate; update: AgentConfigUpdate }>();
  @Output() resetAgent = new EventEmitter<string>();
  @Output() viewTraces = new EventEmitter<string>();

  // Local mutable copy of config
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

    if (this.draftConfig) {
      this.currentModel = this.draftConfig.model ?? this.agent.config.model ?? 'inherit';
      this.currentTemperature = this.draftConfig.temperature ?? this.agent.config.temperature ?? 0.7;
      this.currentTopP = this.draftConfig.top_p ?? this.agent.config.top_p ?? 0.95;
      this.currentMaxTokens = this.draftConfig.max_output_tokens ?? this.agent.config.max_output_tokens ?? 8192;
      this.currentPromptPrefix = this.draftConfig.custom_prompt_prefix ?? '';
    } else {
      this.currentModel = this.agent.config.model || this.agent.config.default_model || 'inherit';
      this.currentTemperature = this.agent.config.temperature ?? this.agent.config.default_temperature ?? 0.7;
      this.currentTopP = this.agent.config.top_p ?? this.agent.config.default_top_p ?? 0.95;
      this.currentMaxTokens = this.agent.config.max_output_tokens ?? this.agent.config.default_max_output_tokens ?? 8192;
      this.currentPromptPrefix = this.agent.config.custom_prompt_prefix || '';
    }
    this.checkIfModified();
  }

  getAllModels(): string[] {
    const baseList = ['inherit', 'gemini-3.7-flash', 'gemini-3.5-flash-lite', 'gemini-2.5-pro', 'gemini-2.5-flash'];
    const merged = Array.from(new Set([...baseList, ...this.availableModels]));
    return merged;
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
    const isMod =
      Boolean(this.draftConfig) ||
      this.currentModel !== cfg.default_model ||
      Math.abs(this.currentTemperature - cfg.default_temperature) > 0.001 ||
      Math.abs(this.currentTopP - cfg.default_top_p) > 0.001 ||
      this.currentMaxTokens !== cfg.default_max_output_tokens ||
      Boolean(this.currentPromptPrefix.trim());

    this.hasUnsavedChanges.set(isMod);
    return isMod;
  }

  onReset(): void {
    this.resetAgent.emit(this.agent.name);
  }

  onViewTraces(): void {
    this.viewTraces.emit(this.agent.name);
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
    return tokens.toLocaleString() + ' tokens';
  }

  getTierBadgeClass(tier: string): string {
    if (tier === 'tier1' || tier === 'Root' || tier === 'Coordinator') {
      return 'badge-tier-1';
    }
    return 'badge-tier-2';
  }

  getTierLabel(tier: string): string {
    if (tier === 'tier1') return 'Tier 1: Orchestrator';
    if (tier === 'tier2') return 'Tier 2: Worker';
    return tier;
  }
}
