import { Component, OnInit, inject, HostListener, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, ProjectSummary, ExportLatexRequest } from '../../../../core/api.service';
import { LoadingIndicatorComponent } from '../../../../shared/loading-indicator/loading-indicator.component';

@Component({
  selector: 'app-export-tab',
  standalone: true,
  imports: [CommonModule, FormsModule, LoadingIndicatorComponent],
  templateUrl: './export-tab.component.html',
  styleUrls: ['./export-tab.component.scss']
})
export class ExportTabComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private apiService = inject(ApiService);
  private cdr = inject(ChangeDetectorRef);

  projectId: string = '';
  summary: ProjectSummary | null = null;
  isLoading = true;

  // LaTeX export state
  isExportingLatex = false;
  latexTemplate: 'ieee' | 'acm' | 'plain' = 'ieee';
  showLatexDialog = false;

  // BibTeX export state
  isExportingBibtex = false;

  // Citation Graph export state
  isExportingGraph = false;

  getEffectiveProjectId(): string {
    const parentId = this.route.parent?.snapshot.paramMap.get('id');
    const selfId = this.route.snapshot.paramMap.get('id');
    if (parentId || selfId) return parentId || selfId || '';
    if (typeof window !== 'undefined' && window.location) {
      const parts = window.location.pathname.split('/projects/');
      if (parts.length > 1) {
        const id = parts[1].split('/')[0];
        if (id) return id;
      }
    }
    return '';
  }

  ngOnInit() {
    this.projectId = this.getEffectiveProjectId();
    if (this.projectId) {
      this.loadSummary();
    } else {
      this.isLoading = false;
    }
    this.route.parent?.paramMap.subscribe(params => {
      const id = params.get('id') || this.getEffectiveProjectId();
      if (id && id !== this.projectId) {
        this.projectId = id;
        this.loadSummary();
      }
    });
  }

  loadSummary() {
    this.isLoading = true;
    this.apiService.getProjectSummary(this.projectId).subscribe({
      next: (summary) => {
        this.summary = summary;
        this.isLoading = false;
        this.cdr.markForCheck();
      },
      error: (err) => {
        console.error('Failed to load project summary', err);
        this.isLoading = false;
        this.cdr.markForCheck();
      }
    });
  }

  get hasPapers(): boolean {
    return !!this.summary && this.summary.paper_count > 0;
  }

  get hasApprovedDrafts(): boolean {
    return !!this.summary && this.summary.has_drafts;
  }

  openLatexDialog() {
    if (!this.hasApprovedDrafts) return;
    this.showLatexDialog = true;
  }

  closeLatexDialog() {
    this.showLatexDialog = false;
  }

  @HostListener('document:keydown.escape')
  handleEscape() {
    if (this.showLatexDialog) {
      this.closeLatexDialog();
    }
  }

  exportLatex() {
    if (!this.projectId) return;
    this.isExportingLatex = true;
    this.closeLatexDialog();

    const request: ExportLatexRequest = { template: this.latexTemplate };
    this.apiService.exportLatex(this.projectId, request).subscribe({
      next: (blob) => {
        this.downloadFile(blob, `project_${this.projectId}_latex.zip`);
        this.isExportingLatex = false;
      },
      error: (err) => {
        console.error('Failed to export LaTeX', err);
        this.isExportingLatex = false;
      }
    });
  }

  exportBibtex() {
    if (!this.hasPapers || !this.projectId) return;
    this.isExportingBibtex = true;

    this.apiService.exportBibtex(this.projectId).subscribe({
      next: (blob) => {
        this.downloadFile(blob, `project_${this.projectId}_bibtex.bib`);
        this.isExportingBibtex = false;
      },
      error: (err) => {
        console.error('Failed to export BibTeX', err);
        this.isExportingBibtex = false;
      }
    });
  }

  exportCitationGraph() {
    if (!this.hasPapers || !this.projectId) return;
    this.isExportingGraph = true;

    this.apiService.exportCitationGraph(this.projectId).subscribe({
      next: (blob) => {
        // Typically a json or zip file
        this.downloadFile(blob, `project_${this.projectId}_citation_graph.json`);
        this.isExportingGraph = false;
      },
      error: (err) => {
        console.error('Failed to export citation graph', err);
        this.isExportingGraph = false;
      }
    });
  }

  /**
   * Shared file download utility function
   * Creates a Blob URL, attaches to an anchor, clicks it, and revokes it.
   */
  private downloadFile(blob: Blob, filename: string) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    
    // Clean up
    setTimeout(() => {
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    }, 100);
  }
}
