import { request } from "./http";

export function fetchSituationOverview({ topLimit } = {}) {
  const qs = topLimit ? `?top_limit=${encodeURIComponent(topLimit)}` : "";
  return request(`/api/situation-overview${qs}`);
}

export function triggerSituationAnalysis() {
  return request("/api/situation-overview/refresh", { method: "POST" });
}
