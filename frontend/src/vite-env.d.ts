/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional override. If unset, API host is derived from window.location.hostname:8000/api */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
