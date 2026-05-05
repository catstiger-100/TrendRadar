import { request } from "./http";

export function fetchSituationOverview() {
  return request("/api/situation-overview");
}
