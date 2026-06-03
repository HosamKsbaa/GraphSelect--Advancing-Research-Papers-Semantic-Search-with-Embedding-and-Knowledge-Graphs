import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, ProjectSummary, OutlineSection } from '../../../../core/api.service';
import { LoadingIndicatorComponent } from '../../../../shared/loading-indicator/loading-indicator.component';
import { EmptyStateComponent } from '../../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-planning-tab',
  standalone: true,
  imports: [CommonModule, FormsModule, LoadingIndicatorComponent, EmptyStateComponent],
  templateUrl: './planning-tab.component.html',
  styleUrl: './planning-tab.component.scss'
})
export class PlanningTabComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private api = inject(ApiService);

  projectId: string = '';
  summary: ProjectSummary | null = null;
  outlineSections: OutlineSection[] = [];
  
  isLoadingSummary = false;
  isGeneratingOutline = false;
  
  // Dialog state
  showConfigDialog = false;
  configStyle = 'academic';
  configNumSections = 5;

  ngOnInit() {
    this.projectId = this.route.parent?.snapshot.paramMap.get('id') || '';
    if (this.projectId) {
      this.loadSummary();
    }
  }

  loadSummary() {
    this.isLoadingSummary = true;
    this.api.getProjectSummary(this.projectId).subscribe({
      next: (summary) => {
        this.summary = summary;
        this.isLoadingSummary = false;
      },
      error: (err) => {
        console.error('Failed to load project summary', err);
        this.isLoadingSummary = false;
      }
    });
  }

  openConfigDialog() {
    this.showConfigDialog = true;
  }
  
  closeConfigDialog() {
    this.showConfigDialog = false;
  }

  generateOutline() {
    this.showConfigDialog = false;
    this.isGeneratingOutline = true;
    
    this.api.generateOutline(this.projectId, {
      style: this.configStyle,
      num_sections: this.configNumSections
    }).subscribe({
      next: (res) => {
        this.outlineSections = res.sections;
        this.isGeneratingOutline = false;
        this.loadSummary(); // refresh summary
      },
      error: (err) => {
        console.error('Failed to generate outline', err);
        this.isGeneratingOutline = false;
      }
    });
  }

  regenerateSection(section: OutlineSection) {
    // In a real application, you might regenerate just this section
    console.log('Regenerate section', section);
  }

  approveSection(section: OutlineSection) {
    console.log('Approve section', section);
  }
}
