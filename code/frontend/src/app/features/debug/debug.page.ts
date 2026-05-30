import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ApiService,
  DebugRetrieveResponse,
  DebugEmbedResponse,
  DebugSimilarityResponse,
} from '../../core/api.service';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'alrs-debug',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './debug.page.html',
  styleUrl: './debug.page.scss',
})
export class DebugPage {
  // --- Paper Retrieval ---
  retrieveDoi = '';
  retrieveLoading = false;
  retrieveResult: DebugRetrieveResponse | null = null;

  // --- Text Embedding ---
  embedText = '';
  embedLoading = false;
  embedResult: DebugEmbedResponse | null = null;

  // --- Cosine Similarity ---
  simTextA = '';
  simTextB = '';
  simLoading = false;
  simResult: DebugSimilarityResponse | null = null;

  constructor(
    private api: ApiService,
    private toast: ToastService,
  ) {}

  // --- Actions ---

  runRetrieve(): void {
    if (!this.retrieveDoi.trim()) return;
    this.retrieveLoading = true;
    this.retrieveResult = null;
    this.api.debugTestRetrieve(this.retrieveDoi.trim()).subscribe({
      next: (res) => {
        this.retrieveResult = res;
        this.retrieveLoading = false;
      },
      error: (err) => {
        this.retrieveResult = {
          success: false,
          elapsed_ms: 0,
          error: err.error?.detail || err.message || 'Request failed',
        };
        this.retrieveLoading = false;
      },
    });
  }

  runEmbed(): void {
    if (!this.embedText.trim()) return;
    this.embedLoading = true;
    this.embedResult = null;
    this.api.debugTestEmbed(this.embedText.trim()).subscribe({
      next: (res) => {
        this.embedResult = res;
        this.embedLoading = false;
        this._checkGeminiError(res.error);
      },
      error: (err) => {
        const errorMsg = err.error?.detail || err.message || 'Request failed';
        this.embedResult = {
          success: false,
          elapsed_ms: 0,
          error: errorMsg,
        };
        this.embedLoading = false;
        this._checkGeminiError(errorMsg);
      },
    });
  }

  runSimilarity(): void {
    if (!this.simTextA.trim() || !this.simTextB.trim()) return;
    this.simLoading = true;
    this.simResult = null;
    this.api.debugTestSimilarity(this.simTextA.trim(), this.simTextB.trim()).subscribe({
      next: (res) => {
        this.simResult = res;
        this.simLoading = false;
        this._checkGeminiError(res.error);
      },
      error: (err) => {
        const errorMsg = err.error?.detail || err.message || 'Request failed';
        this.simResult = {
          success: false,
          elapsed_ms: 0,
          error: errorMsg,
        };
        this.simLoading = false;
        this._checkGeminiError(errorMsg);
      },
    });
  }

  /** Return a 0-100 percentage for the similarity gauge bar */
  getSimilarityPercent(): number {
    if (!this.simResult?.similarity_score) return 0;
    return Math.round(this.simResult.similarity_score * 100);
  }

  /** Return a color class based on similarity score */
  getSimilarityColor(): string {
    const pct = this.getSimilarityPercent();
    if (pct >= 80) return 'gauge-high';
    if (pct >= 50) return 'gauge-medium';
    return 'gauge-low';
  }

  /**
   * Check if a Gemini error occurred (400 / INVALID_ARGUMENT / API key)
   * and show a toast directing the user to the Settings page.
   */
  private _checkGeminiError(error?: string): void {
    if (!error) return;
    const lower = error.toLowerCase();
    if (
      lower.includes('400') ||
      lower.includes('invalid_argument') ||
      lower.includes('api key') ||
      lower.includes('api_key') ||
      lower.includes('invalid api') ||
      lower.includes('permission denied') ||
      lower.includes('unauthenticated')
    ) {
      this.toast.error(
        'Gemini API Key Issue',
        'The Gemini API returned an error. Please check that your API key is valid in Settings.',
        10000,
        { label: 'Go to Settings', routerLink: '/settings' }
      );
    }
  }
}
