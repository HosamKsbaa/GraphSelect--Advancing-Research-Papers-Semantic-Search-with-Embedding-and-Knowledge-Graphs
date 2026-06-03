import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { ApiService } from '../../../core/api.service';

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

  projectId: string = '';
  hasApiKey = true;

  ngOnInit() {
    this.projectId = this.route.snapshot.paramMap.get('id') || '';
    this.api.getSettings().subscribe({
      next: (settings) => {
        this.hasApiKey = !!settings.gemini_api_key_set;
      },
      error: () => {
        this.hasApiKey = false;
      }
    });
  }
}
