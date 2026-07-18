import { HealthResponse, Opportunity } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function getOpportunities(): Promise<Opportunity[]> {
  const response = await fetch(`${API_BASE}/opportunities`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load opportunities");
  }
  return response.json();
}

export async function getOpportunity(id: string): Promise<Opportunity> {
  const response = await fetch(`${API_BASE}/opportunities/${id}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load opportunity");
  }
  return response.json();
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load health");
  }
  return response.json();
}
