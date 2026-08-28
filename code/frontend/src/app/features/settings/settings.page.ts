import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ApiService,
  SettingsResponse,
  SettingsUpdateRequest,
  TestConnectionRequest,
  TestConnectionResponse,
} from '../../core/api.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'alrs-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.page.html',
  styleUrl: './settings.page.scss',
})
export class SettingsPage implements OnInit {
  loading = true;
  saving = false;
  testingConnection = false;
  settings: SettingsResponse | null = null;

  // Active Auth Mode ('studio' vs 'vertex')
  authMode: 'studio' | 'vertex' = 'studio';

  // Form fields (empty = keep current)
  apiBaseUrl = '';
  geminiApiKey = '';
  vertexProject = '';
  vertexLocation = 'us-central1';
  openalexApiKey = '';
  openalexEmail = '';

  // Tiered Multi-Agent Architecture
  tier1Model = 'gemini-2.5-flash';
  tier2Model = 'gemini-3.5-flash-lite';
  availableModels: string[] = [
    'gemini-2.5-flash',
    'gemini-2.5-pro',
    'gemini-3.5-flash',
    'gemini-3.5-flash-lite',
    'gemini-3.1-flash-lite',
  ];

  // Active Architecture Preset
  activePreset: 'speed' | 'balanced' | 'quality' | 'custom' = 'balanced';

  // Toggle visibility for API key inputs
  showGeminiKey = false;
  showOpenalexKey = false;

  // Live Connection Test Results
  testResult: TestConnectionResponse | null = null;

  constructor(
    private api: ApiService,
    private toast: ToastService
  ) {}

  ngOnInit(): void {
    this.apiBaseUrl = this.api.baseUrl;
    this.loadSettings();
  }

  loadSettings(): void {
    this.loading = true;
    this.api.getSettings().subscribe({
      next: (settings) => {
        this.settings = settings;
        this.openalexEmail = settings.openalex_email || '';

        // Sync active mode from backend
        const isVertex =
          Boolean(settings.use_vertex_ai) ||
          settings.mode === 'vertex' ||
          (settings.mode as string) === 'vertex_ai';
        this.authMode = isVertex ? 'vertex' : 'studio';
        this.vertexProject = settings.vertex_project || '';
        this.vertexLocation = settings.vertex_location || 'us-central1';

        // Sync tiered models
        if (settings.adk_tier1_model) {
          this.tier1Model = settings.adk_tier1_model;
        }
        if (settings.adk_tier2_model) {
          this.tier2Model = settings.adk_tier2_model;
        }
        if (settings.available_models && settings.available_models.length > 0) {
          this.availableModels = settings.available_models;
        }
        this.detectPreset();

        this.loading = false;
      },
      error: (err) => {
        this.toast.error(
          'Settings Load Failed',
          err.error?.detail || 'Could not retrieve current settings.'
        );
        this.loading = false;
      },
    });
  }

  detectPreset(): void {
    if (
      this.tier1Model === 'gemini-3.5-flash-lite' &&
      this.tier2Model === 'gemini-3.5-flash-lite'
    ) {
      this.activePreset = 'speed';
    } else if (
      this.tier1Model === 'gemini-2.5-flash' &&
      this.tier2Model === 'gemini-3.5-flash-lite'
    ) {
      this.activePreset = 'balanced';
    } else if (
      this.tier1Model === 'gemini-2.5-pro' &&
      this.tier2Model === 'gemini-2.5-flash'
    ) {
      this.activePreset = 'quality';
    } else {
      this.activePreset = 'custom';
    }
  }

  applyPreset(preset: 'speed' | 'balanced' | 'quality'): void {
    this.activePreset = preset;
    if (preset === 'speed') {
      this.tier1Model = 'gemini-3.5-flash-lite';
      this.tier2Model = 'gemini-3.5-flash-lite';
    } else if (preset === 'balanced') {
      this.tier1Model = 'gemini-2.5-flash';
      this.tier2Model = 'gemini-3.5-flash-lite';
    } else if (preset === 'quality') {
      this.tier1Model = 'gemini-2.5-pro';
      this.tier2Model = 'gemini-2.5-flash';
    }
  }

  onTierModelChange(): void {
    this.detectPreset();
  }

  setMode(mode: 'studio' | 'vertex'): void {
    this.authMode = mode;
    this.testResult = null;
    this.showGeminiKey = false;
  }

  toggleGeminiVisibility(): void {
    this.showGeminiKey = !this.showGeminiKey;
  }

  toggleOpenalexVisibility(): void {
    this.showOpenalexKey = !this.showOpenalexKey;
  }

  testConnection(): void {
    this.testingConnection = true;
    this.testResult = null;

    const payload: TestConnectionRequest = {
      mode: this.authMode,
    };

    if (this.authMode === 'studio') {
      if (this.geminiApiKey.trim()) {
        payload.gemini_api_key = this.geminiApiKey.trim();
      }
    } else {
      if (this.vertexProject.trim()) {
        payload.vertex_project = this.vertexProject.trim();
      }
      if (this.vertexLocation.trim()) {
        payload.vertex_location = this.vertexLocation.trim();
      }
    }

    this.api.testConnection(payload).subscribe({
      next: (res) => {
        this.testingConnection = false;
        this.testResult = res;
        if (res.success) {
          const latencyBadge = res.latency_ms ? ` (${res.latency_ms}ms)` : '';
          this.toast.success(
            'Connection Verified',
            `${res.message || 'Connection established successfully'}${latencyBadge}`
          );
        } else {
          this.toast.error(
            'Connection Test Failed',
            res.error || res.message || 'Unable to connect with provided credentials.'
          );
        }
      },
      error: (err) => {
        this.testingConnection = false;
        const msg = err.error?.detail || err.error?.error || err.message || 'Network error during connection test.';
        this.testResult = {
          success: false,
          message: 'Connection failed',
          error: msg,
          details: 'Check your API key or network connection and retry.',
        };
        this.toast.error('Connection Test Error', msg);
      },
    });
  }

  saveSettings(): void {
    this.saving = true;

    // Save frontend-only settings immediately
    if (this.apiBaseUrl.trim()) {
      this.api.setBaseUrl(this.apiBaseUrl);
    }

    const body: SettingsUpdateRequest = {
      mode: this.authMode,
      use_vertex_ai: this.authMode === 'vertex',
      openalex_email: this.openalexEmail.trim(),
      adk_tier1_model: this.tier1Model,
      adk_tier2_model: this.tier2Model,
    };

    if (this.authMode === 'studio') {
      if (this.geminiApiKey.trim()) {
        body.gemini_api_key = this.geminiApiKey.trim();
      }
    } else {
      if (this.vertexProject.trim()) {
        body.vertex_project = this.vertexProject.trim();
      }
      if (this.vertexLocation.trim()) {
        body.vertex_location = this.vertexLocation.trim();
      }
    }

    if (this.openalexApiKey.trim()) {
      body.openalex_api_key = this.openalexApiKey.trim();
    }

    this.api.updateSettings(body).subscribe({
      next: (res) => {
        this.saving = false;
        if (res.success !== false) {
          this.toast.success('Settings Saved', res.message || 'Settings saved successfully.');
          // Clear candidate key inputs after save
          this.geminiApiKey = '';
          this.openalexApiKey = '';
          this.showGeminiKey = false;
          this.showOpenalexKey = false;
          this.testResult = null;
          // Reload to get updated previews and state
          this.loadSettings();
        } else {
          this.toast.error('Save Failed', res.message || 'Could not save settings.');
        }
      },
      error: (err) => {
        this.saving = false;
        this.toast.error(
          'Save Failed',
          err.error?.detail || err.error?.message || 'Could not save settings.'
        );
      },
    });
  }
}
