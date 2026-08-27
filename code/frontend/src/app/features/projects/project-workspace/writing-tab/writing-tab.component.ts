import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { 
  ApiService, 
  OutlineSection, 
  ReviewResponse, 
  DraftRequest, 
  ReviewRequest 
} from '../../../../core/api.service';
import { MarkdownPreviewComponent } from '../../../../shared/markdown-preview/markdown-preview.component';
import { LoadingIndicatorComponent } from '../../../../shared/loading-indicator/loading-indicator.component';

export interface SectionDraftState {
  section: OutlineSection;
  status: 'not_started' | 'drafted' | 'reviewed' | 'approved';
  draft_text: string | null;
  review: ReviewResponse | null;
  revision_count: number;
}

import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-writing-tab',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, MarkdownPreviewComponent, LoadingIndicatorComponent, EmptyStateComponent],
  templateUrl: './writing-tab.component.html',
  styleUrls: ['./writing-tab.component.scss']
})
export class WritingTabComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);

  projectId: string = '';
  sections: SectionDraftState[] = [];
  selectedSection: SectionDraftState | null = null;

  isDrafting = false;
  isReviewing = false;
  editMode = false;
  editedDraftText = '';

  ngOnInit() {
    this.route.parent?.paramMap.subscribe(params => {
      this.projectId = params.get('id') || '';
      if (this.projectId) {
        this.loadOutline();
      }
    });
  }

  loadOutline() {
    this.api.getOutline(this.projectId).subscribe({
      next: (res: any) => {
        if (res && res.sections && Array.isArray(res.sections)) {
          this.sections = res.sections.map((sec: OutlineSection) => ({
            section: sec,
            status: 'not_started',
            draft_text: null,
            review: null,
            revision_count: 0
          }));
        } else {
          this.sections = [];
        }
      },
      error: () => {
        this.sections = [];
      }
    });
  }

  get allApproved(): boolean {
    return this.sections.length > 0 && this.sections.every(s => s.status === 'approved');
  }

  selectSection(section: SectionDraftState) {
    this.selectedSection = section;
    this.editMode = false;
    this.editedDraftText = section.draft_text || '';
  }

  toggleEditMode() {
    this.editMode = !this.editMode;
    if (!this.editMode && this.selectedSection) {
      this.selectedSection.draft_text = this.editedDraftText;
      if (this.selectedSection.status === 'approved' || this.selectedSection.status === 'reviewed') {
        this.selectedSection.status = 'drafted';
        this.selectedSection.review = null;
      }
    }
  }

  draftSection() {
    if (!this.selectedSection || !this.projectId) return;

    this.isDrafting = true;
    let context = '';
    if (this.selectedSection.review && this.selectedSection.review.feedback.length > 0) {
      context = `Please address the following feedback in this revision:\n` + this.selectedSection.review.feedback.join('\n');
    }

    const req: DraftRequest = {
      section_title: this.selectedSection.section.title,
      section_description: this.selectedSection.section.description,
      paper_dois: this.selectedSection.section.paper_dois,
      target_level: 'master', // Hardcoded fallback; would ideally come from ProjectContext
      outline_context: context || undefined
    };

    this.api.draftSection(this.projectId, req).subscribe({
      next: (res) => {
        if (this.selectedSection) {
          this.selectedSection.draft_text = res.draft_text;
          this.selectedSection.status = 'drafted';
          this.selectedSection.review = null;
          this.editedDraftText = res.draft_text;
        }
        this.isDrafting = false;
      },
      error: (err) => {
        console.error('Failed to draft section', err);
        this.isDrafting = false;
      }
    });
  }

  reviewSection() {
    if (!this.selectedSection || !this.projectId || !this.selectedSection.draft_text) return;

    this.isReviewing = true;
    const req: ReviewRequest = {
      section_title: this.selectedSection.section.title,
      draft_text: this.selectedSection.draft_text,
      paper_dois: this.selectedSection.section.paper_dois,
      target_level: 'master' // Hardcoded fallback
    };

    this.api.reviewSection(this.projectId, req).subscribe({
      next: (res) => {
        if (this.selectedSection) {
          this.selectedSection.review = res;
          this.selectedSection.status = res.approved ? 'approved' : 'reviewed';
        }
        this.isReviewing = false;
      },
      error: (err) => {
        console.error('Failed to review section', err);
        this.isReviewing = false;
      }
    });
  }

  reviseSection() {
    if (!this.selectedSection) return;
    if (this.selectedSection.revision_count >= 3) {
      alert('Maximum revision count (3) reached for this section.');
      return;
    }
    this.selectedSection.revision_count++;
    this.draftSection();
  }
}
