import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

export interface Toast {
  id: number;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  duration: number;
  action?: { label: string; routerLink: string };
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private _counter = 0;
  private _toasts$ = new Subject<Toast>();
  private _dismiss$ = new Subject<number>();

  /** Observable stream of new toasts */
  get toasts$() {
    return this._toasts$.asObservable();
  }

  /** Observable stream of dismissed toast IDs */
  get dismiss$() {
    return this._dismiss$.asObservable();
  }

  show(
    type: Toast['type'],
    title: string,
    message: string,
    duration = 6000,
    action?: Toast['action']
  ): number {
    const id = ++this._counter;
    this._toasts$.next({ id, type, title, message, duration, action });
    return id;
  }

  success(title: string, message: string, duration = 5000): number {
    return this.show('success', title, message, duration);
  }

  error(title: string, message: string, duration = 8000, action?: Toast['action']): number {
    return this.show('error', title, message, duration, action);
  }

  warning(title: string, message: string, duration = 6000, action?: Toast['action']): number {
    return this.show('warning', title, message, duration, action);
  }

  info(title: string, message: string, duration = 5000): number {
    return this.show('info', title, message, duration);
  }

  dismiss(id: number): void {
    this._dismiss$.next(id);
  }
}
