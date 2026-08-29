import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import {
  TierManagementService,
  ModelTier,
  TierCreateRequest,
  TierUpdateRequest,
  TierListResponse,
  TierDeleteResponse,
  FALLBACK_SYSTEM_TIERS,
} from './tier-management.service';
import { ApiService } from './api.service';

describe('TierManagementService', () => {
  let service: TierManagementService;
  let httpMock: HttpTestingController;
  let apiService: ApiService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        TierManagementService,
        ApiService,
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    service = TestBed.inject(TierManagementService);
    httpMock = TestBed.inject(HttpTestingController);
    apiService = TestBed.inject(ApiService);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created with fallback system tiers', () => {
    expect(service).toBeTruthy();
    expect(service.tiers().length).toBe(FALLBACK_SYSTEM_TIERS.length);
  });

  it('should load tiers via GET /agents/tiers', () => {
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
        name: 'Tier Custom',
        description: 'Custom specialized tier',
        model: 'gemini-2.5-pro',
        temperature: 0.4,
        top_p: 0.9,
        max_output_tokens: 16384,
        color: '#f59e0b',
        is_system: false,
      },
    ];

    const mockResponse: TierListResponse = {
      tiers: mockTiers,
      total: 2,
    };

    service.loadTiers().subscribe((res) => {
      expect(res.tiers.length).toBe(2);
      expect(service.tiers().length).toBe(2);
      expect(service.tiers()[1].id).toBe('tier_custom');
    });

    const req = httpMock.expectOne(`${apiService.baseUrl}/agents/tiers`);
    expect(req.request.method).toBe('GET');
    req.flush(mockResponse);
  });

  it('should create a custom tier via POST /agents/tiers', () => {
    const dto: TierCreateRequest = {
      name: 'Tier Writing Lab',
      description: 'Dedicated writing tier',
      model: 'gemini-2.5-pro',
      temperature: 0.6,
      top_p: 0.95,
      max_output_tokens: 16384,
      color: '#ec4899',
    };

    const createdTier: ModelTier = {
      id: 'tier_writing_lab',
      name: dto.name,
      description: dto.description || '',
      model: dto.model,
      temperature: dto.temperature || 0.7,
      top_p: dto.top_p || 0.95,
      max_output_tokens: dto.max_output_tokens || 8192,
      color: dto.color || '#3b82f6',
      is_system: false,
    };

    service.createTier(dto).subscribe((res) => {
      expect(res.id).toBe('tier_writing_lab');
      expect(service.tiers().some((t) => t.id === 'tier_writing_lab')).toBe(true);
    });

    const req = httpMock.expectOne(`${apiService.baseUrl}/agents/tiers`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(dto);
    req.flush(createdTier);
  });

  it('should update an existing tier via PUT /agents/tiers/{id}', () => {
    const updateDto: TierUpdateRequest = {
      model: 'gemini-3.7-flash',
      temperature: 0.8,
    };

    const updatedTier: ModelTier = {
      ...FALLBACK_SYSTEM_TIERS[0],
      model: 'gemini-3.7-flash',
      temperature: 0.8,
    };

    service.updateTier('tier1', updateDto).subscribe((res) => {
      expect(res.model).toBe('gemini-3.7-flash');
      const tier1 = service.getTierById('tier1');
      expect(tier1?.model).toBe('gemini-3.7-flash');
    });

    const req = httpMock.expectOne(`${apiService.baseUrl}/agents/tiers/tier1`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual(updateDto);
    req.flush(updatedTier);
  });

  it('should delete a custom tier via DELETE /agents/tiers/{id}', () => {
    // Add custom tier first
    const customTier: ModelTier = {
      id: 'tier_to_delete',
      name: 'Delete Me',
      description: 'Temporary',
      model: 'gemini-2.5-flash',
      temperature: 0.7,
      top_p: 0.95,
      max_output_tokens: 8192,
      color: '#f59e0b',
      is_system: false,
    };
    service.tiers.update((list) => [...list, customTier]);
    expect(service.tiers().some((t) => t.id === 'tier_to_delete')).toBe(true);

    const mockDelResponse: TierDeleteResponse = {
      status: 'deleted',
      tier_id: 'tier_to_delete',
      reassigned_agents_count: 1,
      reassigned_to_tier_id: 'tier1',
      message: 'Tier deleted',
    };

    service.deleteTier('tier_to_delete').subscribe((res) => {
      expect(res.status).toBe('deleted');
      expect(service.tiers().some((t) => t.id === 'tier_to_delete')).toBe(false);
    });

    const req = httpMock.expectOne(`${apiService.baseUrl}/agents/tiers/tier_to_delete`);
    expect(req.request.method).toBe('DELETE');
    req.flush(mockDelResponse);
  });

  it('should manage editor modal state with openEditor and closeEditor', () => {
    expect(service.isEditorOpen()).toBe(false);
    expect(service.editingTier()).toBeNull();

    service.openEditor(FALLBACK_SYSTEM_TIERS[0]);
    expect(service.isEditorOpen()).toBe(true);
    expect(service.editingTier()?.id).toBe('tier1');

    service.closeEditor();
    expect(service.isEditorOpen()).toBe(false);
    expect(service.editingTier()).toBeNull();
  });
});
