import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { ToastContainerComponent } from './core/toast-container.component';

@Component({
  selector: 'alrs-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ToastContainerComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  title = 'ALRS v2';
  currentYear = new Date().getFullYear();
  version = '3.0.0-alpha.1';
}
