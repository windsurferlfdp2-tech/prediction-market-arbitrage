import type { ModelStatus } from "./types";

export function modelStatusLabel(status: ModelStatus): string;
export function canApproveModel(status: ModelStatus): boolean;
export function canRetireModel(status: ModelStatus): boolean;
export function shortId(value?: string | null): string;
export function dateOnly(value?: string | null): string;
