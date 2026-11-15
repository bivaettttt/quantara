import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e",
  workers: 1,
  timeout: 65000,
  use: {
    baseURL: process.env.QUANTARA_URL ?? "http://127.0.0.1:8151",
    viewport: { width: 1500, height: 950 },
    video: process.env.QUANTARA_VIDEO ? "on" : "off",
  },
});
