import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError, timeout, TimeoutError } from 'rxjs';
import { ToastService } from './toast.service';

export const apiInterceptor: HttpInterceptorFn = (req, next) => {
  const toastService = inject(ToastService);

  // Identify LLM-powered endpoints
  const isLlmEndpoint = 
    req.url.includes('/analysis/') && req.url.includes('/gap-queries') ||
    req.url.includes('/planning/') ||
    req.url.includes('/writing/');

  let requestStream = next(req);

  if (isLlmEndpoint) {
    // Add 60s timeout for LLM endpoints
    requestStream = requestStream.pipe(
      timeout(60000)
    );
  }

  return requestStream.pipe(
    catchError((error) => {
      if (error instanceof TimeoutError) {
        toastService.warning(
          'Request Timeout',
          'The AI request took longer than 60 seconds and was timed out. Please try again or refine your query.'
        );
      } else if (error instanceof HttpErrorResponse) {
        if (error.status === 0) {
          toastService.error('Backend Unreachable', 'Unable to connect to the server. Please check if the backend is running.');
        } else {
          let errorMsg = error.message;
          if (error.error) {
            const raw = error.error.detail ?? error.error.message ?? error.error;
            if (typeof raw === 'string') {
              errorMsg = raw;
            } else if (Array.isArray(raw)) {
              errorMsg = raw
                .map((item: any) => {
                  if (typeof item === 'string') return item;
                  if (item?.msg) {
                    const field = item.loc && Array.isArray(item.loc) && item.loc.length > 0
                      ? `${item.loc[item.loc.length - 1]}: `
                      : '';
                    return `${field}${item.msg}`;
                  }
                  return JSON.stringify(item);
                })
                .join('; ');
            } else if (typeof raw === 'object' && raw !== null) {
              errorMsg = JSON.stringify(raw);
            }
          }
          toastService.error(`API Error (${error.status})`, errorMsg);
        }
      } else {
        toastService.error('Unknown Error', 'An unexpected error occurred.');
      }
      return throwError(() => error);
    })
  );
};
