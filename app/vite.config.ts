import { defineConfig } from "vite";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import yaml from "yaml";

const host = process.env.TAURI_DEV_HOST;

// Read config.yaml from project root at build/dev time
const configPath = path.resolve(import.meta.dirname, "../config.yaml");
let appConfig: Record<string, any> = {};
if (fs.existsSync(configPath)) {
  const fileContent = fs.readFileSync(configPath, "utf-8");
  appConfig = yaml.parse(fileContent) || {};
}

// https://vite.dev/config/
export default defineConfig(() => ({
  define: {
    // Only what the frontend reads; anything else in config.yaml stays out of the bundle (H-054)
    __APP_CONFIG__: JSON.stringify({
      hotkey: appConfig.hotkey,
      window: appConfig.window,
      behavior: { hide_after_seconds: appConfig.behavior?.hide_after_seconds },
      live2d: appConfig.live2d,
    }),
  },
  // Two pages: Miku's window and the panel
  build: {
    rolldownOptions: {
      input: {
        main: path.resolve(import.meta.dirname, "index.html"),
        panel: path.resolve(import.meta.dirname, "panel.html"),
      },
    },
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || "127.0.0.1", // not exposed to the LAN during development (H-054)
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : true,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
}));
