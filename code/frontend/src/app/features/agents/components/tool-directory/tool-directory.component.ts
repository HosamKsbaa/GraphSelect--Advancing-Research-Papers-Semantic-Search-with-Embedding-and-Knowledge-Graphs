import { Component, Input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AgentToolDefinition, ToolParameterProperty } from '../../../../core/agent.service';
import { MarkdownPreviewComponent } from '../../../../shared/markdown-preview/markdown-preview.component';

@Component({
  selector: 'app-tool-directory',
  standalone: true,
  imports: [CommonModule, MarkdownPreviewComponent],
  templateUrl: './tool-directory.component.html',
  styleUrl: './tool-directory.component.scss',
})
export class ToolDirectoryComponent {
  @Input() tools: AgentToolDefinition[] = [];
  @Input() agentName = '';

  expandedTools = signal<Record<string, boolean>>({});
  schemaViewMode = signal<Record<string, 'visual' | 'json'>>({});
  copiedToolName = signal<string | null>(null);

  isToolExpanded(toolName: string): boolean {
    return !!this.expandedTools()[toolName];
  }

  toggleTool(toolName: string): void {
    this.expandedTools.update((prev) => ({
      ...prev,
      [toolName]: !prev[toolName],
    }));
  }

  expandAll(): void {
    const all: Record<string, boolean> = {};
    for (const tool of this.tools) {
      all[tool.name] = true;
    }
    this.expandedTools.set(all);
  }

  collapseAll(): void {
    this.expandedTools.set({});
  }

  getViewMode(toolName: string): 'visual' | 'json' {
    return this.schemaViewMode()[toolName] || 'visual';
  }

  setViewMode(toolName: string, mode: 'visual' | 'json'): void {
    this.schemaViewMode.update((prev) => ({
      ...prev,
      [toolName]: mode,
    }));
  }

  getPropertiesList(tool: AgentToolDefinition): { name: string; prop: ToolParameterProperty; isRequired: boolean }[] {
    if (!tool.parameters || !tool.parameters.properties) {
      return [];
    }
    const required = tool.parameters.required || [];
    return Object.entries(tool.parameters.properties).map(([name, prop]) => ({
      name,
      prop: prop as ToolParameterProperty,
      isRequired: required.includes(name),
    }));
  }

  formatJsonSchema(tool: AgentToolDefinition): string {
    try {
      return JSON.stringify(tool.parameters, null, 2);
    } catch {
      return '{}';
    }
  }

  copySchema(tool: AgentToolDefinition, event?: MouseEvent): void {
    if (event) {
      event.stopPropagation();
    }
    const json = this.formatJsonSchema(tool);
    navigator.clipboard.writeText(json).then(() => {
      this.copiedToolName.set(tool.name);
      setTimeout(() => {
        if (this.copiedToolName() === tool.name) {
          this.copiedToolName.set(null);
        }
      }, 2000);
    });
  }
}
