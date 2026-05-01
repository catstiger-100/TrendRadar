import { request } from "./http";

export function fetchNews(params = {}) {
  const query = new URLSearchParams();
  if (params.keyword) query.set("keyword", params.keyword);
  if (params.date) query.set("date", params.date);
  if (params.source) query.set("source", params.source);
  query.set("page", params.page || 1);
  query.set("page_size", params.page_size || 200);
  return request(`/api/news?${query.toString()}`);
}

export function fetchSources() {
  return request("/api/news/sources-list");
}
