export const API = "/api";

export async function fetchJSON(path, signal) {
  const response = await fetch(`${API}${path}`, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
