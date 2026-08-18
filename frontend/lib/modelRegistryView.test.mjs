import assert from "node:assert/strict";
import test from "node:test";

import {
  canApproveModel,
  canRetireModel,
  dateOnly,
  modelStatusLabel,
  shortId
} from "./modelRegistryView.js";

test("approved model status renders as Approved", () => {
  assert.equal(modelStatusLabel("approved_for_paper"), "Approved");
});

test("approved models cannot be approved again", () => {
  assert.equal(canApproveModel("approved_for_paper"), false);
  assert.equal(canApproveModel("candidate"), true);
  assert.equal(canApproveModel("rejected"), true);
});

test("retired models cannot be approved or retired again", () => {
  assert.equal(canApproveModel("retired"), false);
  assert.equal(canRetireModel("retired"), false);
});

test("model registry compact values are stable", () => {
  assert.equal(shortId("model-1234567890abcdef"), "model-123456");
  assert.equal(shortId(null), "n/a");
  assert.equal(dateOnly("2026-01-24T06:00:00Z"), "2026-01-24");
  assert.equal(dateOnly(null), "n/a");
});
