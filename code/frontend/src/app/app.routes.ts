import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'projects',
    pathMatch: 'full',
  },
  {
    path: 'system-status',
    loadComponent: () =>
      import('./features/system-status/system-status.page').then(m => m.SystemStatusPage),
  },
  {
    path: 'projects',
    loadComponent: () =>
      import('./features/projects/project-list/project-list.page').then(m => m.ProjectListPage),
  },
  {
    path: 'projects/:id',
    loadComponent: () =>
      import('./features/projects/project-workspace/project-workspace.page').then(m => m.ProjectWorkspacePage),
    children: [
      { path: '', redirectTo: 'research', pathMatch: 'full' },
      { path: 'research', loadComponent: () => import('./features/projects/project-workspace/research-tab/research-tab.component').then(m => m.ResearchTabComponent) },
      { path: 'analysis', loadComponent: () => import('./features/projects/project-workspace/analysis-tab/analysis-tab.component').then(m => m.AnalysisTabComponent) },
      { path: 'planning', loadComponent: () => import('./features/projects/project-workspace/planning-tab/planning-tab.component').then(m => m.PlanningTabComponent) },
      { path: 'writing', loadComponent: () => import('./features/projects/project-workspace/writing-tab/writing-tab.component').then(m => m.WritingTabComponent) },
      { path: 'chat', loadComponent: () => import('./features/projects/project-workspace/chat-tab/chat-tab.component').then(m => m.ChatTabComponent) },
      { path: 'export', loadComponent: () => import('./features/projects/project-workspace/export-tab/export-tab.component').then(m => m.ExportTabComponent) },
    ]
  },
  {
    path: 'search',
    loadComponent: () =>
      import('./features/search/search.page').then(m => m.SearchPage),
  },
  {
    path: 'sessions',
    loadComponent: () =>
      import('./features/sessions/sessions.page').then(m => m.SessionsPage),
  },
  {
    path: 'logs',
    loadComponent: () =>
      import('./features/logs/logs.page').then(m => m.LogsPage),
  },
  {
    path: 'debug',
    loadComponent: () =>
      import('./features/debug/debug.page').then(m => m.DebugPage),
  },
  {
    path: 'settings',
    loadComponent: () =>
      import('./features/settings/settings.page').then(m => m.SettingsPage),
  },
];
