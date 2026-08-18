export class ApiConfigurationError extends Error {}
export function normalizeApiBaseUrl(value?: string): string;
export function getApiBaseUrl(): string;
export function buildApiUrl(path: string, baseUrl?: string): URL;
