import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { TierEditorModalComponent } from './tier-editor-modal.component';
import { TierManagementService, ModelTier } from '../../../../core/tier-management.service';
import { ToastService } from '../../../../core/toast.service';

describe('TierEditorModalComponent', () => {
  let component: TierEditorModalComponent;
  let fixture: ComponentFixture<TierEditorModalComponent>;
  let tierServiceMock: any;
  let toastMock: any;

  const mockTiers: ModelTier[] = [
    {
      id: 'tier1',
      name: 'Tier 1: Orchestration',
      description: 'Orchestration tier',
      model: 'gemini-2.5-flash',
      temperature: 0.7,
      top_p: 0.95,
      max_output_tokens: 8192,
      color: '#6366f1',
      is_system: true,
    },
    {
      id: 'tier_custom',
      name: 'Tier Custom Lab',
      description: 'Custom lab tier',
      model: 'gemini-2.5-pro',
      temperature: 0.5,
      top_p: 0.95,
      max_output_tokens: 16384,
      color: '#f59e0b',
      is_system: false,
    },
  ];

  beforeEach(async () => {
    tierServiceMock = {
      tiers: vi.fn().mockReturnValue(mockTiers),
      editingTier: vi.fn().mockReturnValue(null),
      createTier: vi.fn(),
      updateTier: vi.fn(),
      deleteTier: vi.fn(),
      loadTiers: vi.fn().mockReturnValue(of({ tiers: mockTiers, total: 2 })),
    };

    toastMock = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [TierEditorModalComponent],
      providers: [
        { provide: TierManagementService, useValue: tierServiceMock },
        { provide: ToastService, useValue: toastMock },
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(TierEditorModalComponent);
    component = fixture.componentInstance;
    component.isOpen = true;
    fixture.detectChanges();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  it('should display list of tiers', () => {
    expect(component.tiers().length).toBe(2);
    expect(component.formMode()).toBe('list');
  });

  it('should transition to create mode when startCreate is called', () => {
    component.startCreate();
    expect(component.formMode()).toBe('create');
    expect(component.formName).toBe('');
    expect(component.formColor).toBe('#f59e0b');
  });

  it('should transition to edit mode with selected tier fields', () => {
    component.startEdit(mockTiers[0]);
    expect(component.formMode()).toBe('edit');
    expect(component.formId).toBe('tier1');
    expect(component.formName).toBe('Tier 1: Orchestration');
    expect(component.formModel).toBe('gemini-2.5-flash');
    expect(component.formTemperature).toBe(0.7);
  });

  it('should submit tier creation and emit event', () => {
    component.startCreate();
    component.formName = 'Tier 4: Super Fast';
    component.formModel = 'gemini-3.5-flash-lite';
    component.formTemperature = 0.1;

    const createdTier: ModelTier = {
      id: 'tier_4_super_fast',
      name: 'Tier 4: Super Fast',
      description: '',
      model: 'gemini-3.5-flash-lite',
      temperature: 0.1,
      top_p: 0.95,
      max_output_tokens: 8192,
      color: '#f59e0b',
      is_system: false,
    };

    tierServiceMock.createTier.mockReturnValue(of(createdTier));

    let emittedTier: ModelTier | null = null;
    component.tierCreated.subscribe((t) => {
      emittedTier = t;
    });

    component.saveTier();

    expect(tierServiceMock.createTier).toHaveBeenCalled();
    expect(toastMock.success).toHaveBeenCalledWith('Tier Created', expect.any(String));
    expect(emittedTier).toEqual(createdTier);
    expect(component.formMode()).toBe('list');
  });

  it('should prompt deletion for custom tier and execute delete on confirm', () => {
    component.promptDelete(mockTiers[1]);
    expect(component.deleteConfirmTier()).toBe(mockTiers[1]);

    tierServiceMock.deleteTier.mockReturnValue(
      of({
        status: 'deleted',
        tier_id: 'tier_custom',
        reassigned_agents_count: 2,
        reassigned_to_tier_id: 'tier1',
      })
    );

    let deletedId: string | null = null;
    component.tierDeleted.subscribe((id) => {
      deletedId = id;
    });

    component.confirmDelete();

    expect(tierServiceMock.deleteTier).toHaveBeenCalledWith('tier_custom');
    expect(deletedId).toBe('tier_custom');
    expect(component.deleteConfirmTier()).toBeNull();
  });

  it('should prevent deleting system default tiers', () => {
    component.promptDelete(mockTiers[0]);
    expect(toastMock.info).toHaveBeenCalledWith('System Tier', expect.any(String));
    expect(component.deleteConfirmTier()).toBeNull();
  });
});
