import { Component, OnInit, inject, HostListener, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { ApiService } from '../../../core/api.service';
import { ToastService } from '../../../core/toast.service';
import { AuthModalService } from '../../../core/auth-modal.service';

@Component({
  selector: 'app-project-workspace',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './project-workspace.page.html',
  styleUrls: ['./project-workspace.page.scss']
})
export class ProjectWorkspacePage implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private toastService = inject(ToastService);
  public authModalService = inject(AuthModalService);

  projectId: string = '';
  hasApiKey = computed(() => this.authModalService.hasValidCredentials());

  openCredentialsModal(): void {
    this.authModalService.open();
  }

  openAuthModal(): void {
    this.authModalService.open();
  }

  ngOnInit() {
    this.projectId = this.route.snapshot.paramMap.get('id') || '';
    this.route.paramMap.subscribe(params => {
      const id = params.get('id');
      if (id) {
        this.projectId = id;
        this.projectPath = '';
        this.api.touchProject(this.projectId).subscribe({
          error: (err) => console.error('Failed to update last accessed time:', err)
        });
      }
    });

    this.authModalService.refreshAuthStatus().subscribe({
      error: () => {}
    });

    if (this.projectId) {
      this.api.touchProject(this.projectId).subscribe({
        error: (err) => console.error('Failed to update last accessed time:', err)
      });
    }
  }

  showFolderPopover = false;
  projectPath = '';
  loadingPath = false;
  copied = false;

  toggleFolderPopover() {
    this.showFolderPopover = !this.showFolderPopover;
    if (this.showFolderPopover && !this.projectPath) {
      this.fetchProjectPath();
    }
  }

  @HostListener('document:keydown.escape')
  handleEscape() {
    if (this.showFolderPopover) {
      this.showFolderPopover = false;
    }
  }

  fetchProjectPath() {
    if (!this.projectId) return;
    this.loadingPath = true;
    this.api.openProjectFolder(this.projectId).subscribe({
      next: (res) => {
        this.projectPath = res.path;
        this.loadingPath = false;
        // Auto-copy on first fetch for convenience
        this.copyToClipboard(res.path, false);
      },
      error: (err) => {
        this.loadingPath = false;
        this.toastService.error('Error', err.error?.detail || 'Failed to fetch project folder path');
      }
    });
  }

  copyToClipboard(text: string, showToast = true) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      this.copied = true;
      if (showToast) {
        this.toastService.success('Copied', 'Folder path copied to clipboard');
      }
      setTimeout(() => {
        this.copied = false;
      }, 2000);
    }).catch((err) => {
      console.error('Failed to copy to clipboard:', err);
      this.toastService.error('Copy Failed', 'Failed to copy path to clipboard');
    });
  }
}
