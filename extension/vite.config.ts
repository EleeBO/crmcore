import preact from "@preact/preset-vite";
import { defineConfig } from "vite";
import webExtension from "vite-plugin-web-extension";

export default defineConfig({
  plugins: [
    preact(),
    webExtension({
      manifest: "manifest.json",
      additionalInputs: [
        "src/offscreen/offscreen.html",
        "src/permissions/permissions.html",
        "src/settings/evaluation-settings.html",
        "src/report/report.html",
      ],
    }),
  ],
});
