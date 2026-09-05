import type { AsaasCheckoutResponse, BillingPlansResponse, UserProfile } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return response.json();
}

export const getBillingPlans = () => request<BillingPlansResponse>("/api/billing/plans");
export const getCurrentUser = () => request<UserProfile>("/api/auth/me");
export const registerTrial = (name: string, email: string, password: string, companyName?: string) =>
  request<UserProfile>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password, company_name: companyName || undefined }),
  });
export const createPlanCheckout = (planCode: string, billingCycle: "monthly" | "yearly") =>
  request<AsaasCheckoutResponse>("/api/billing/asaas/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_code: planCode, billing_cycle: billingCycle }),
  });
