import { defineConfig } from "vite";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import yaml from "yaml";

const host = process.env.TAURI_DEV_HOST;

// Read config.yaml from project root at build/dev time
const configPath = path.resolve(import.meta.dirname, "../config.yaml");
let appConfig = {};
if (fs.existsSync(configPath)) {
  const fileContent = fs.readFileSync(configPath, "utf-8");
  appConfig = yaml.parse(fileContent) || {};
}

// https://vite.dev/config/
export default defineConfig(() => ({
  define: {
    __APP_CONFIG__: JSON.stringify(appConfig),
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || "0.0.0.0",
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
