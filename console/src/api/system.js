import { request } from "./http";

export function fetchRoles() {
  return request("/api/roles");
}

export function createRole(payload) {
  return request("/api/roles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateRole(id, payload) {
  return request(`/api/roles/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteRole(id) {
  return request(`/api/roles/${id}`, {
    method: "DELETE",
  });
}

export function fetchUsers() {
  return request("/api/users");
}

export function createUser(payload) {
  return request("/api/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateUser(id, payload) {
  return request(`/api/users/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteUser(id) {
  return request(`/api/users/${id}`, {
    method: "DELETE",
  });
}

export function fetchAiModels() {
  return request("/api/ai-models");
}

export function updateAiModels(payload) {
  return request("/api/ai-models", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function testAiModel(payload) {
  return request("/api/ai-models/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchFuturesSymbols() {
  return request("/api/futures-symbols");
}

export function createFuturesSymbol(payload) {
  return request("/api/futures-symbols", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateFuturesSymbol(id, payload) {
  return request(`/api/futures-symbols/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteFuturesSymbol(id) {
  return request(`/api/futures-symbols/${id}`, {
    method: "DELETE",
  });
}
