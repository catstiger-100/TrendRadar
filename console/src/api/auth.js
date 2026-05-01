import { request } from "./http";

export function login(payload) {
  return request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logout() {
  return request("/api/auth/logout", {
    method: "POST",
  });
}

export function fetchMe() {
  return request("/api/auth/me");
}

export function changePassword(payload) {
  return request("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
