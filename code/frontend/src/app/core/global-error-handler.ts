import { ErrorHandler, Injectable, Injector, NgZone } from '@angular/core';
import { ToastService } from './toast.service';

@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  constructor(private injector: Injector, private zone: NgZone) {}

  handleError(error: any): void {
    const toastService = this.injector.get(ToastService);
    const message = error.message ? error.message : error.toString();
    
    this.zone.run(() => {
      toastService.error('Application Error', message);
    });
    
    console.error('Error from GlobalErrorHandler:', error);
  }
}
