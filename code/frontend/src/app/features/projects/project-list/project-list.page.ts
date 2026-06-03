import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, Project, ProjectCreateRequest } from '../../../core/api.service';
import { RelativeTimePipe } from '../../../shared/relative-time.pipe';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

@Component({
  selector: 'app-project-list',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, RelativeTimePipe, EmptyStateComponent],
  templateUrl: './project-list.page.html',
  styleUrls: ['./project-list.page.scss']
})
export class ProjectListPage implements OnInit {
  projects: Project[] = [];
  masterProjects: Project[] = [];
  phdProjects: Project[] = [];
  archivedProjects: Project[] = [];
  
  showArchived = false;
  searchQuery = '';
  isLoading = false;

  // Dialog State
  showCreateDialog = false;
  newProject: ProjectCreateRequest = {
    name: '',
    description: '',
    topic: '',
    target_level: 'master'
  };
  isCreating = false;

  constructor(private apiService: ApiService, private router: Router) {}

  ngOnInit() {
    this.loadProjects();
  }

  loadProjects() {
    this.isLoading = true;
    this.apiService.listProjects(this.showArchived).subscribe({
      next: (response) => {
        this.projects = response;
        this.filterAndGroupProjects();
        this.isLoading = false;
      },
      error: (err) => {
        console.error('Failed to load projects', err);
        this.isLoading = false;
      }
    });
  }

  filterAndGroupProjects() {
    let filtered = this.projects;
    
    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase();
      filtered = filtered.filter(p => 
        p.name.toLowerCase().includes(q) || 
        (p.topic && p.topic.toLowerCase().includes(q)) ||
        (p.description && p.description.toLowerCase().includes(q))
      );
    }

    if (!this.showArchived) {
      filtered = filtered.filter(p => !p.is_archived);
      this.archivedProjects = [];
    } else {
      this.archivedProjects = filtered.filter(p => p.is_archived);
      filtered = filtered.filter(p => !p.is_archived);
    }

    this.masterProjects = filtered.filter(p => p.target_level === 'master');
    this.phdProjects = filtered.filter(p => p.target_level === 'phd');
  }

  onSearchChange() {
    this.filterAndGroupProjects();
  }

  toggleArchived() {
    this.showArchived = !this.showArchived;
    this.loadProjects();
  }

  openCreateDialog() {
    this.newProject = {
      name: '',
      description: '',
      topic: '',
      target_level: 'master'
    };
    this.showCreateDialog = true;
  }

  closeCreateDialog() {
    this.showCreateDialog = false;
  }

  createProject() {
    if (!this.newProject.name.trim()) return;

    this.isCreating = true;
    this.apiService.createProject(this.newProject).subscribe({
      next: (project) => {
        this.isCreating = false;
        this.closeCreateDialog();
        this.router.navigate(['/projects', project.id]);
      },
      error: (err) => {
        console.error('Failed to create project', err);
        this.isCreating = false;
      }
    });
  }
}
