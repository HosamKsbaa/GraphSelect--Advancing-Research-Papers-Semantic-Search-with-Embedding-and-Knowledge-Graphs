import { Component, EventEmitter, Input, OnInit, Output, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ModelTier,
  TierCreateRequest,
  TierManagementService,
  TierUpdateRequest,
} from '../../../../core/tier-management.service';
import { ToastService } from '../../../../core/toast.service';

@Component({
  selector: 'app-tier-editor-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './tier-editor-modal.component.html',
  styleUrl: './tier-editor-modal.component.scss',
})
export class TierEditorModalComponent implements OnInit {
  tierService = inject(TierManagementService);
  private toast = inject(ToastService);

  @Input() isOpen = false;
  @Input() availableModels: string[] = [
    'gemini-3.7-flash',
    'gemini-3.5-flash',
    'gemini-3.5-flash-lite',
    'gemini-2.5-pro',
    'gemini-2.5-flash',
  ];

  @Output() close = new EventEmitter<void>();
  @Output() tierUpdated = new EventEmitter<ModelTier>();
  @Output() tierCreated = new EventEmitter<ModelTier>();
  @Output() tierDeleted = new EventEmitter<string>();

  // Available color swatch presets
  colorPresets = [
    { label: 'Indigo', hex: '#6366f1' },
    { label: 'Emerald', hex: '#10b981' },
    { label: 'Purple', hex: '#a855f7' },
    { label: 'Cyan', hex: '#06b6d4' },
    { label: 'Amber', hex: '#f59e0b' },
    { label: 'Rose', hex: '#f43f5e' },
    { label: 'Blue', hex: '#3b82f6' },
    { label: 'Slate', hex: '#64748b' },
  ];

  // Active form mode ('list' | 'create' | 'edit')
  formMode = signal<'list' | 'create' | 'edit'>('list');

  // Form State
  formId = '';
  formName = '';
  formDescription = '';
  formModel = 'gemini-2.5-flash';
  formTemperature = 0.7;
  formTopP = 0.95;
  formMaxTokens = 8192;
  formColor = '#6366f1';

  // Submitting / Processing State
  submitting = signal<boolean>(false);
  deleteConfirmTier = signal<ModelTier | null>(null);

  // Computed
  tiers = computed(() => this.tierService.tiers());
  selectedTier = computed(() => this.tierService.editingTier());

  ngOnInit(): void {
    if (this.tierService.editingTier()) {
      this.startEdit(this.tierService.editingTier()!);
    }
  }

  getFilteredModels(): string[] {
    const list = this.availableModels.filter((m) => m !== 'inherit');
    if (list.length === 0) {
      return ['gemini-2.5-flash', 'gemini-3.5-flash-lite', 'gemini-2.5-pro', 'gemini-3.7-flash'];
    }
    return list;
  }

  startCreate(): void {
    this.formMode.set('create');
    this.formId = '';
    this.formName = '';
    this.formDescription = '';
    this.formModel = this.getFilteredModels()[0] || 'gemini-2.5-flash';
    this.formTemperature = 0.7;
    this.formTopP = 0.95;
    this.formMaxTokens = 8192;
    this.formColor = this.colorPresets[4].hex; // Amber for custom
    this.deleteConfirmTier.set(null);
  }

  startEdit(tier: ModelTier): void {
    this.formMode.set('edit');
    this.formId = tier.id;
    this.formName = tier.name;
    this.formDescription = tier.description || '';
    this.formModel = tier.model;
    this.formTemperature = tier.temperature;
    this.formTopP = tier.top_p;
    this.formMaxTokens = tier.max_output_tokens;
    this.formColor = tier.color || '#3b82f6';
    this.deleteConfirmTier.set(null);
  }

  cancelForm(): void {
    this.formMode.set('list');
    this.deleteConfirmTier.set(null);
  }

  onClose(): void {
    this.formMode.set('list');
    this.deleteConfirmTier.set(null);
    this.close.emit();
  }

  saveTier(): void {
    const name = this.formName.trim();
    if (!name) {
      this.toast.warning('Validation Error', 'Tier name is required.');
      return;
    }

    this.submitting.set(true);

    if (this.formMode() === 'create') {
      const createDto: TierCreateRequest = {
        id: this.formId.trim() || undefined,
        name,
        description: this.formDescription.trim() || undefined,
        model: this.formModel,
        temperature: Number(this.formTemperature),
        top_p: Number(this.formTopP),
        max_output_tokens: Number(this.formMaxTokens),
        color: this.formColor,
      };

      this.tierService.createTier(createDto).subscribe({
        next: (created) => {
          this.submitting.set(false);
          this.toast.success('Tier Created', `Created custom tier "${created.name}".`);
          this.tierCreated.emit(created);
          this.formMode.set('list');
        },
        error: (err) => {
          this.submitting.set(false);
          this.toast.error('Tier Creation Failed', err?.error?.detail || err?.message || 'Could not create tier.');
        },
      });
    } else if (this.formMode() === 'edit') {
      const updateDto: TierUpdateRequest = {
        name,
        description: this.formDescription.trim() || undefined,
        model: this.formModel,
        temperature: Number(this.formTemperature),
        top_p: Number(this.formTopP),
        max_output_tokens: Number(this.formMaxTokens),
        color: this.formColor,
      };

      this.tierService.updateTier(this.formId, updateDto).subscribe({
        next: (updated) => {
          this.submitting.set(false);
          this.toast.success('Tier Updated', `Updated "${updated.name}" defaults.`);
          this.tierUpdated.emit(updated);
          this.formMode.set('list');
        },
        error: (err) => {
          this.submitting.set(false);
          this.toast.error('Tier Update Failed', err?.error?.detail || err?.message || 'Could not update tier.');
        },
      });
    }
  }

  promptDelete(tier: ModelTier): void {
    if (tier.is_system) {
      this.toast.info('System Tier', 'System default tiers cannot be deleted.');
      return;
    }
    this.deleteConfirmTier.set(tier);
  }

  cancelDelete(): void {
    this.deleteConfirmTier.set(null);
  }

  confirmDelete(): void {
    const tier = this.deleteConfirmTier();
    if (!tier) return;

    this.submitting.set(true);
    this.tierService.deleteTier(tier.id).subscribe({
      next: (res) => {
        this.submitting.set(false);
        this.deleteConfirmTier.set(null);
        this.toast.success(
          'Tier Deleted',
          `Deleted tier "${tier.name}". ${res.reassigned_agents_count} member agent(s) reassigned to Tier 1.`
        );
        this.tierDeleted.emit(tier.id);
        if (this.formMode() === 'edit' && this.formId === tier.id) {
          this.formMode.set('list');
        }
      },
      error: (err) => {
        this.submitting.set(false);
        this.toast.error('Delete Failed', err?.error?.detail || err?.message || 'Could not delete tier.');
      },
    });
  }

  getTempBadgeClass(temp: number): string {
    if (temp <= 0.3) return 'temp-deterministic';
    if (temp <= 0.8) return 'temp-balanced';
    return 'temp-creative';
  }

  formatTokens(tokens: number): string {
    return Number(tokens).toLocaleString() + ' tokens';
  }
}
