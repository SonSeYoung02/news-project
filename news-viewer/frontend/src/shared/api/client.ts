export const API = "/api";

export class HttpError extends Error {
  status: number;

  constructor(status: number) {
    super(`HTTP ${status}`);
    this.name = "HttpError";
    this.status = status;
  }
}

// 응답 본문은 검증하지 않고 호출자가 지정한 타입으로 취급한다.
export async function fetchJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API}${path}`, { signal });
  if (!response.ok) throw new HttpError(response.status);
  return response.json() as Promise<T>;
}
