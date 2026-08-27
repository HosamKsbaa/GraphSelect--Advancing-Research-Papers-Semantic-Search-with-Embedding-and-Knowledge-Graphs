import {
  Component,
  ElementRef,
  HostListener,
  ViewChild,
  OnInit,
  effect,
  ChangeDetectorRef,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthModalService, AuthMode } from '../../core/auth-modal.service';
import {
  ApiService,
  TestConnectionResponse,
  SettingsUpdateRequest,
} from '../../core/api.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-api-key-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './api-key-modal.component.html',
  styleUrl: './api-key-modal.component.scss',
})
export class ApiKeyModalComponent implements OnInit {
  activeTab: 'studio' | 'vertex' = 'studio';

  // Form Model State
  geminiApiKey = '';
  vertexProject = '';
  vertexLocation = 'us-central1';

  // UI State
  showGeminiKey = false;
  isTesting = false;
  isSaving = false;
  testResult: TestConnectionResponse | null = null;

  @ViewChild('geminiKeyInput') geminiKeyInputRef?: ElementRef<HTMLInputElement>;
  @ViewChild('vertexProjectInput') vertexProjectInputRef?: ElementRef<HTMLInputElement>;
  @ViewChild('saveBtn') saveBtnRef?: ElementRef<HTMLButtonElement>;

  constructor(
    public authModal: AuthModalService,
    private api: ApiService,
    private toast: ToastService,
    private cdr: ChangeDetectorRef
  ) {
    // Synchronize active tab whenever service mode changes or modal opens
    effect(() => {
      const isOpen = this.authModal.isOpen();
      if (isOpen) {
        const mode = this.authModal.activeMode();
        this.activeTab = (mode === 'vertex' || (mode as string) === 'vertex_ai') ? 'vertex' : 'studio';
        this.showGeminiKey = false;
        this.testResult = null;
        this.syncWithCurrentStatus();
      }
      this.cdr.markForCheck();
    });
  }

  ngOnInit(): void {
    this.syncWithCurrentStatus();
  }

  syncWithCurrentStatus(): void {
    const status = this.authModal.authStatus();
    if (status) {
      if (status.vertex_project) {
        this.vertexProject = status.vertex_project;
      }
      if (status.vertex_location) {
        this.vertexLocation = status.vertex_location;
      }
    }
  }

  setMode(mode: 'studio' | 'vertex'): void {
    this.activeTab = mode;
    this.authModal.setMode(mode);
    // Reset key visibility when toggling modes (as tested in test_tier2_mask_toggle_resets_on_mode_switch)
    this.showGeminiKey = false;
    this.testResult = null;
  }

  toggleGeminiKey(): void {
    this.showGeminiKey = !this.showGeminiKey;
  }

  testConnection(): void {
    // Boundary check for empty inputs before sending probe
    if (this.activeTab === 'studio') {
      const currentConfigured = this.authModal.authStatus()?.gemini_api_key_set;
      if (!this.geminiApiKey.trim() && !currentConfigured) {
        this.testResult = {
          success: false,
          message: 'Connection failed',
          error: 'Gemini API key is required. Please provide a valid key.',
        };
        return;
      }
    } else {
      const currentConfigured = this.authModal.authStatus()?.use_vertex_ai && this.authModal.authStatus()?.vertex_project;
      if (!this.vertexProject.trim() && !currentConfigured) {
        this.testResult = {
          success: false,
          message: 'Connection failed',
          error: 'Google Cloud Project ID is required for Vertex AI mode.',
        };
        return;
      }
    }

    this.isTesting = true;
    this.testResult = null;

    const payload = {
      mode: this.activeTab,
      gemini_api_key: this.activeTab === 'studio' && this.geminiApiKey.trim() ? this.geminiApiKey.trim() : undefined,
      vertex_project: this.activeTab === 'vertex' && this.vertexProject.trim() ? this.vertexProject.trim() : undefined,
      vertex_location: this.activeTab === 'vertex' && this.vertexLocation.trim() ? this.vertexLocation.trim() : 'us-central1',
    };

    this.api.testConnection(payload).subscribe({
      next: (res) => {
        this.isTesting = false;
        this.testResult = res;
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.isTesting = false;
        this.testResult = {
          success: false,
          message: 'Connection test failed',
          error: err.error?.detail || err.error?.error || err.message || 'Unknown network error',
        };
        this.cdr.markForCheck();
      },
    });
  }

  saveAndApply(): void {
    this.isSaving = true;

    const body: SettingsUpdateRequest = {
      mode: this.activeTab,
      use_vertex_ai: this.activeTab === 'vertex',
    };

    if (this.activeTab === 'studio') {
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

    // Call updateSettings to update .env and hot-swap services
    this.api.updateSettings(body).subscribe({
      next: (res) => {
        this.isSaving = false;
        if (res.success !== false) {
          this.toast.success(
            'Credentials Saved',
            this.activeTab === 'vertex'
              ? 'Vertex AI credentials configured successfully.'
              : 'Google AI Studio API key configured successfully.'
          );
          // Refresh auth status in service, clear temporary inputs, and close
          this.authModal.hasValidCredentials.set(true);
          this.authModal.refreshAuthStatus().subscribe();
          this.geminiApiKey = '';
          this.close();
        } else {
          this.toast.error('Save Failed', res.message || 'Could not save credentials.');
        }
      },
      error: (err) => {
        this.isSaving = false;
        this.toast.error(
          'Save Failed',
          err.error?.detail || err.error?.message || 'Could not save credentials.'
        );
      },
    });
  }

  close(): void {
    this.geminiApiKey = '';
    this.testResult = null;
    this.authModal.close();
    this.cdr.markForCheck();
  }

  onBackdropClick(event: MouseEvent): void {
    // Only dismiss if clicking directly on the backdrop overlay
    const target = event.target as HTMLElement;
    if (target.classList.contains('modal-backdrop') || target.classList.contains('dialog-backdrop')) {
      this.close();
    }
  }

  @HostListener('document:keydown.escape', ['$event'])
  handleEscape(event?: Event): void {
    if (this.authModal.isOpen()) {
      if (event) {
        event.preventDefault();
      }
      this.close();
    }
  }
}
