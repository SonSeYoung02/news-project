import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { resetViewportMock } from "./helpers/mockApi.ts";

resetViewportMock();

if (typeof HTMLElement !== "undefined" && !HTMLElement.prototype.scrollTo) {
  HTMLElement.prototype.scrollTo = () => {};
}

if (typeof window !== "undefined" && !window.requestAnimationFrame) {
  window.requestAnimationFrame = (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(performance.now()), 0);
  window.cancelAnimationFrame = (handle: number) => {
    window.clearTimeout(handle);
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  resetViewportMock();
});
