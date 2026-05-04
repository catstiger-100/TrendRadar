import { request } from "./http";

export function fetchNews(params = {}) {
  const query = new URLSearchParams();
  if (params.keyword) query.set("keyword", params.keyword);
  if (params.date) query.set("date", params.date);
  if (params.source) query.set("source", params.source);
  if (params.favorite_only) query.set("favorite_only", "1");
  query.set("page", params.page || 1);
  query.set("page_size", params.page_size || 200);
  return request(`/api/news?${query.toString()}`);
}

export function fetchSources() {
  return request("/api/news/sources-list");
}

export function createFavorite(payload) {
  return request("/api/news/favorites", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteFavorite(articleId) {
  return request(`/api/news/favorites/${articleId}`, {
    method: "DELETE",
  });
}

export function createOrUpdateShare(payload) {
  return request("/api/news/shares", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchShare(articleId) {
  return request(`/api/news/shares?article_id=${articleId}`);
}

export function fetchPublicShare(token) {
  return request(`/api/public/shares/${token}`);
}

export function interpretArticle(articleId) {
  return request("/api/news/interpret", {
    method: "POST",
    body: JSON.stringify({ article_id: articleId }),
  });
}
