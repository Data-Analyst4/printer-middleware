export class MiddlewareHttpError extends Error {
  readonly status: number;
  readonly statusText: string;
  readonly responseText: string;

  constructor(status: number, statusText: string, responseText: string) {
    super(`Middleware HTTP ${status} ${statusText}`);
    this.name = "MiddlewareHttpError";
    this.status = status;
    this.statusText = statusText;
    this.responseText = responseText;
  }
}
