import type { ApiErrorResponse } from "@/types/api";

export class ApiError extends Error {
  readonly code: string;
  readonly details: unknown;
  readonly status: number;

  constructor(code: string, message: string, details: unknown = null, status = 400) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
    this.status = status;
  }

  static async fromResponse(res: Response): Promise<ApiError> {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      return new ApiError("HTTP_ERROR", res.statusText || "request failed", null, res.status);
    }
    const err = (body as ApiErrorResponse | undefined)?.error;
    if (err && typeof err.code === "string" && typeof err.message === "string") {
      return new ApiError(err.code, err.message, err.details ?? null, res.status);
    }
    return new ApiError("HTTP_ERROR", res.statusText || "request failed", body, res.status);
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "request failed";
}
