import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'alrs-logs',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './logs.page.html',
  styleUrl: './logs.page.scss',
})
export class LogsPage {
  // API log viewer will be connected to /api/logs endpoints once backend supports it
}
