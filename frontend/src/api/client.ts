import { getSession } from './session';

/** Backend HTTP port when deriving API URL from the page host (Vite UI is typically :5173). */
const DEFAULT_API_PORT = '8000';

/**
 * Resolve API base URL (including `/api`).
 * Priority: 1) VITE_API_BASE_URL  2) same host as the browser, port 8000
 * so LAN / VPN / Windows Server IPs work without hardcoding.
 */
export function resolveApiBaseUrl(): string {
  const fromEnv = String(import.meta.env.VITE_API_BASE_URL || '').trim();
  if (fromEnv) {
    return fromEnv.replace(/\/$/, '');
  }
  if (typeof window !== 'undefined' && window.location?.hostname) {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:${DEFAULT_API_PORT}/api`;
  }
  return `http://localhost:${DEFAULT_API_PORT}/api`;
}

function apiBaseUrl(): string {
  return resolveApiBaseUrl();
}

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function buildHeaders(extra?: HeadersInit, isFormData = false): Headers {
  const headers = new Headers(extra);
  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const session = getSession();
  if (session) {
    headers.set('X-User-Role', session.role);
    headers.set('X-User-Name', session.name);
  }
  return headers;
}

async function parseError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  let code: string | undefined;
  let details: unknown;

  try {
    const body = await response.json();
    if (body?.error?.message) {
      message = body.error.message;
      code = body.error.code;
      details = body.error.details;
    } else if (body?.detail) {
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      details = body.detail;
    } else if (body?.message) {
      message = body.message;
    }
  } catch {
    // ignore JSON parse failures
  }

  const statusMessages: Record<number, string> = {
    400: 'Bad request',
    401: 'Unauthorized',
    403: 'You do not have permission to perform this action',
    404: 'Resource not found',
    409: 'Conflict — resource already exists',
    422: 'Validation failed',
    500: 'Server error — please try again later',
  };

  if (message.startsWith('Request failed') && statusMessages[response.status]) {
    message = statusMessages[response.status];
  }

  return new ApiError(message, response.status, code, details);
}

export type RequestOptions = {
  method?: string;
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
  params?: Record<string, string | number | boolean | undefined | null>;
};

function withQuery(path: string, params?: RequestOptions['params']): string {
  if (!params) return path;
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    qs.set(key, String(value));
  });
  const query = qs.toString();
  return query ? `${path}?${query}` : path;
}

const CONNECTION_ERROR_MESSAGE =
  'Unable to connect to the server. Please verify the server is running and reachable.';

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${apiBaseUrl()}${withQuery(path.startsWith('/') ? path : `/${path}`, options.params)}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method || 'GET',
      headers: buildHeaders(options.headers),
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (err) {
    // CORS preflight failures, connection refused, offline, DNS, etc. never yield a Response.
    throw new ApiError(CONNECTION_ERROR_MESSAGE, 0, 'NETWORK_ERROR', err);
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export async function apiUpload<T>(
  path: string,
  file: File,
  fieldName = 'file',
  onProgress?: (percent: number) => void
): Promise<T> {
  const url = `${apiBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`;

  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);

    const session = getSession();
    if (session) {
      xhr.setRequestHeader('X-User-Role', session.role);
      xhr.setRequestHeader('X-User-Name', session.name);
    }

    xhr.upload.onprogress = event => {
      if (!onProgress || !event.lengthComputable) return;
      onProgress(Math.round((event.loaded / event.total) * 100));
    };

    xhr.onload = () => {
      const ok = xhr.status >= 200 && xhr.status < 300;
      try {
        const body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
        if (!ok) {
          const message =
            body?.error?.message ||
            body?.detail ||
            body?.message ||
            `Upload failed (${xhr.status})`;
          reject(
            new ApiError(
              typeof message === 'string' ? message : JSON.stringify(message),
              xhr.status,
              body?.error?.code,
              body?.error?.details ?? body?.detail
            )
          );
          return;
        }
        resolve(body as T);
      } catch (err) {
        reject(err);
      }
    };

    xhr.onerror = () => reject(new ApiError('Network error during upload', 0));

    const form = new FormData();
    form.append(fieldName, file);
    xhr.send(form);
  });
}

export function getApiBaseUrl(): string {
  return apiBaseUrl();
}
