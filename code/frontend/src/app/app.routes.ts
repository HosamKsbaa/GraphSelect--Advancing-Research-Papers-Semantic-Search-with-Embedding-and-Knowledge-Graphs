import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full',
  },
  {
    path: 'dashboard',
    loadComponent: () =>
      import('./features/dashboard/dashboard.page').then(m => m.DashboardPage),
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
];
