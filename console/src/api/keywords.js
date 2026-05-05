import { request } from "./http";

export function fetchKeywords() {
  return request("/api/keywords");
}

export function saveKeywords(content) {
  return request("/api/keywords", {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function uploadKeywords(file) {
  const formData = new FormData();
  formData.append("file", file);
  return fetch("/api/keywords/upload", {
    method: "POST",
    credentials: "include",
    body: formData,
  }).then(async (res) => {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = new Error(data.error || "上传失败");
      error.status = res.status;
      throw error;
    }
    return data;
  });
}

export function fetchBackups() {
  return request("/api/keywords/backups");
}

export function downloadTemplate(format) {
  return `/api/keywords/template/${format}`;
}
