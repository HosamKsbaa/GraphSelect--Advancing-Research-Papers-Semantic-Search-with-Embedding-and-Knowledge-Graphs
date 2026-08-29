import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AgentConfigUpdate, AgentMetadata } from '../../../../core/agent.service';
import { AgentCardComponent } from '../agent-card/agent-card.component';

@Component({
  selector: 'app-agent-drawer',
  standalone: true,
  imports: [CommonModule, AgentCardComponent],
  templateUrl: './agent-drawer.component.html',
  styleUrl: './agent-drawer.component.scss',
})
export class AgentDrawerComponent {
  @Input() agent: AgentMetadata | null = null;
  @Input() isOpen = false;
  @Input() availableModels: string[] = [];
  @Input() draftConfig?: AgentConfigUpdate;
  @Input() isSaving = false;

  @Output() close = new EventEmitter<void>();
  @Output() configChange = new EventEmitter<{
    agentName: string;
    config: AgentConfigUpdate;
    update: AgentConfigUpdate;
  }>();
  @Output() resetAgent = new EventEmitter<string>();
  @Output() viewTraces = new EventEmitter<string>();
  @Output() saveAgent = new EventEmitter<string>();

  onClose(): void {
    this.close.emit();
  }

  onConfigChange(event: {
    agentName: string;
    config: AgentConfigUpdate;
    update: AgentConfigUpdate;
  }): void {
    this.configChange.emit(event);
  }

  onResetAgent(agentName: string): void {
    this.resetAgent.emit(agentName);
  }

  onViewTraces(agentName: string): void {
    this.viewTraces.emit(agentName);
  }

  onSaveClick(): void {
    if (this.agent) {
      this.saveAgent.emit(this.agent.name);
    }
  }
}
