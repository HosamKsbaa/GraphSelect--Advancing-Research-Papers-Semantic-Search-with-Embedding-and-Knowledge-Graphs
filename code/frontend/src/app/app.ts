import { Component, inject } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { ToastContainerComponent } from './core/toast-container.component';
import { ApiKeyModalComponent } from './shared/api-key-modal/api-key-modal.component';
import { AuthModalService } from './core/auth-modal.service';

@Component({
  selector: 'alrs-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    ToastContainerComponent,
    ApiKeyModalComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  public authModalService = inject(AuthModalService);
  title = 'ALRS v2';
  currentYear = new Date().getFullYear();
  version = '3.0.0-alpha.1';
}
