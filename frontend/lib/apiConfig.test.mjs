import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiConfigurationError,
  buildApiUrl,
  normalizeApiBaseUrl
} from "./apiConfig.js";

test("missing NEXT_PUBLIC_API_URL reports local env file instructions", () => {
  assert.throws(
    () => normalizeApiBaseUrl(undefined),
    (error) =>
      error instanceof ApiConfigurationError &&
      error.message.includes("Missing NEXT_PUBLIC_API_URL") &&
      error.message.includes("frontend/.env.local") &&
      error.message.includes("Restart the frontend")
  );
});

test("valid NEXT_PUBLIC_API_URL is accepted", () => {
  assert.equal(normalizeApiBaseUrl("http://127.0.0.1:8000"), "http://127.0.0.1:8000");
});

test("trailing slash is removed", () => {
  assert.equal(normalizeApiBaseUrl("http://127.0.0.1:8000/"), "http://127.0.0.1:8000");
});

test("invalid URL is rejected", () => {
  assert.throws(
    () => normalizeApiBaseUrl("not a url"),
    /Invalid NEXT_PUBLIC_API_URL/
  );
});

test("non-http URL is rejected", () => {
  assert.throws(
    () => normalizeApiBaseUrl("file:///tmp/api"),
    /Invalid NEXT_PUBLIC_API_URL/
  );
});

test("health request URL is constructed from the API base", () => {
  assert.equal(
    buildApiUrl("/health", "http://127.0.0.1:8000").toString(),
    "http://127.0.0.1:8000/health"
  );
});

test("candidate-generation request URL is constructed from the API base", () => {
  assert.equal(
    buildApiUrl("/market-matches/generate", "http://127.0.0.1:8000").toString(),
    "http://127.0.0.1:8000/market-matches/generate"
  );
});

test("paper-trade request URL is constructed from the API base", () => {
  assert.equal(
    buildApiUrl("/model-paper-trades/run", "http://127.0.0.1:8000").toString(),
    "http://127.0.0.1:8000/model-paper-trades/run"
  );
});
