import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ApiService,
  SettingsResponse,
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
  settings: SettingsResponse | null = null;

  // Form fields (empty = keep current)
  apiBaseUrl = '';
  geminiApiKey = '';
  openalexApiKey = '';
  openalexEmail = '';

  // Toggle visibility for API key inputs
  showGeminiKey = false;
  showOpenalexKey = false;

  constructor(
    private api: ApiService,
    private toast: ToastService,
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

  saveSettings(): void {
    this.saving = true;

    // Save frontend-only settings immediately
    if (this.apiBaseUrl.trim()) {
      this.api.setBaseUrl(this.apiBaseUrl);
    }

    const body: Record<string, string> = {};

    if (this.geminiApiKey.trim()) {
      body['gemini_api_key'] = this.geminiApiKey.trim();
    }
    if (this.openalexApiKey.trim()) {
      body['openalex_api_key'] = this.openalexApiKey.trim();
    }
    // Always send email (can be cleared)
    body['openalex_email'] = this.openalexEmail.trim();

    this.api.updateSettings(body).subscribe({
      next: (res) => {
        this.saving = false;
        if (res.success) {
          this.toast.success('Settings Saved', res.message);
          // Clear key fields after save
          this.geminiApiKey = '';
          this.openalexApiKey = '';
          this.showGeminiKey = false;
          this.showOpenalexKey = false;
          // Reload to get updated previews
          this.loadSettings();
        } else {
          this.toast.error('Save Failed', res.message);
        }
      },
      error: (err) => {
        this.saving = false;
        this.toast.error(
          'Save Failed',
          err.error?.detail || 'Could not save settings.'
        );
      },
    });
  }

  toggleGeminiVisibility(): void {
    this.showGeminiKey = !this.showGeminiKey;
  }

  toggleOpenalexVisibility(): void {
    this.showOpenalexKey = !this.showOpenalexKey;
  }
}
