import { Injectable, signal, computed } from '@angular/core';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { ApiService, AuthStatusResponse, SettingsResponse } from './api.service';

export type AuthMode = 'studio' | 'vertex' | 'google_ai_studio' | 'vertex_ai';

@Injectable({ providedIn: 'root' })
export class AuthModalService {
  /** Reactive signal indicating whether the modal pop-up is currently open */
  readonly isOpen = signal<boolean>(false);

  /** Reactive signal indicating whether credentials are configured and valid */
  readonly hasValidCredentials = signal<boolean>(false);

  /** Reactive signal for active mode selection in UI ('studio' or 'vertex') */
  readonly activeMode = signal<AuthMode>('studio');

  /** Full cached auth status response from backend */
  readonly authStatus = signal<AuthStatusResponse | null>(null);

  /** Computed boolean alias for fast conditional gating */
  readonly isConfigured = computed(() => this.hasValidCredentials());

  /** Computed boolean alias matching spec contract */
  readonly hasCredentials = computed(() => this.hasValidCredentials());

  /** Computed string for current mode */
  readonly currentMode = computed(() => this.authStatus()?.mode ?? this.activeMode());

  constructor(private api: ApiService) {
    this.refreshAuthStatus().subscribe({
      error: () => {
        // Silently handle startup failures (e.g. mock server or disconnected backend)
      },
    });
  }

  /**
   * Open the credential modal dialog.
   * Optionally set the active provider mode on open.
   */
  open(initialMode?: AuthMode): void {
    if (initialMode) {
      const normalized: AuthMode = (initialMode === 'vertex' || (initialMode as string) === 'vertex_ai') ? 'vertex' : 'studio';
      this.activeMode.set(normalized);
    }
    this.isOpen.set(true);
    this.refreshAuthStatus().subscribe({
      error: () => {},
    });
  }

  /**
   * Close the credential modal dialog.
   */
  close(): void {
    this.isOpen.set(false);
  }

  /**
   * Toggle modal visibility.
   */
  toggle(): void {
    this.isOpen.update((v) => !v);
  }

  /**
   * Set active mode programmatically.
   */
  setMode(mode: AuthMode): void {
    const normalized: AuthMode = (mode === 'vertex' || (mode as string) === 'vertex_ai') ? 'vertex' : 'studio';
    this.activeMode.set(normalized);
  }

  /**
   * Set valid credentials boolean signal directly.
   */
  setCredentialsState(valid: boolean): void {
    this.hasValidCredentials.set(valid);
  }

  /**
   * Fetch current backend auth status and update all reactive signals.
   */
  refreshAuthStatus(): Observable<AuthStatusResponse> {
    return this.api.getAuthStatus().pipe(
      tap((status) => {
        this.authStatus.set(status);
        this.hasValidCredentials.set(Boolean(status.has_credentials));
        if (!this.isOpen()) {
          const isVertex = status.mode === 'vertex' || (status.mode as string) === 'vertex_ai' || Boolean(status.use_vertex_ai);
          this.activeMode.set(isVertex ? 'vertex' : 'studio');
        }
      })
    );
  }

  /**
   * Synchronize state from SettingsResponse.
   */
  updateFromSettingsResponse(res: SettingsResponse): void {
    const isVertex = res.use_vertex_ai || res.mode === 'vertex' || (res.mode as string) === 'vertex_ai';
    const hasCreds = Boolean(res.has_credentials ?? (isVertex ? res.vertex_project : res.gemini_api_key_set));
    
    const status: AuthStatusResponse = {
      mode: isVertex ? 'vertex' : 'studio',
      has_credentials: hasCreds,
      gemini_api_key_preview: res.gemini_api_key_preview,
      gemini_api_key_set: Boolean(res.gemini_api_key_set),
      vertex_project: res.vertex_project ?? null,
      vertex_location: res.vertex_location || 'us-central1',
      use_vertex_ai: Boolean(isVertex),
      openalex_api_key_preview: res.openalex_api_key_preview ?? null,
      openalex_api_key_set: Boolean(res.openalex_api_key_set),
      openalex_email: res.openalex_email || '',
    };
    
    this.authStatus.set(status);
    this.hasValidCredentials.set(hasCreds);
  }
}
