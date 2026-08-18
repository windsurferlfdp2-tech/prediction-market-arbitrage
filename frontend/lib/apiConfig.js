const REQUIRED_API_URL = "http://127.0.0.1:8000";
const ENV_FILE_PATH = "frontend/.env.local";

export class ApiConfigurationError extends Error {
  constructor(message) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

export function normalizeApiBaseUrl(value) {
  if (!value) {
    throw new ApiConfigurationError(
      [
        "Missing NEXT_PUBLIC_API_URL.",
        `Expected ${ENV_FILE_PATH} to contain NEXT_PUBLIC_API_URL=${REQUIRED_API_URL}.`,
        "Restart the frontend after editing the file."
      ].join(" ")
    );
  }
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new ApiConfigurationError(
      "Invalid NEXT_PUBLIC_API_URL. Use a valid http:// or https:// URL."
    );
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new ApiConfigurationError(
      "Invalid NEXT_PUBLIC_API_URL. Use a valid http:// or https:// URL."
    );
  }
  return url.origin;
}

export function getApiBaseUrl() {
  return normalizeApiBaseUrl(process.env.NEXT_PUBLIC_API_URL);
}

export function buildApiUrl(path, baseUrl = getApiBaseUrl()) {
  return new URL(path, baseUrl);
}
