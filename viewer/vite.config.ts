/// <reference types="vitest" />
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const DATA_ROOT = path.join(REPO_ROOT, "data");

// Stream files from <repo_root>/data/* at /data/* during dev so the viewer
// can <video src="/data/video1.mp4"> and fetch("/data/session.jsonl") without
// symlinking or copying anything into viewer/public.
function serveRepoData(): Plugin {
  return {
    name: "serve-repo-data",
    configureServer(server) {
      server.middlewares.use("/data", (req, res, next) => {
        const reqPath = (req.url ?? "").split("?")[0];
        const filePath = path.join(DATA_ROOT, reqPath);
        if (!filePath.startsWith(DATA_ROOT)) {
          res.statusCode = 403;
          res.end("Forbidden");
          return;
        }
        fs.stat(filePath, (err, stat) => {
          if (err || !stat.isFile()) {
            next();
            return;
          }
          const ext = path.extname(filePath).toLowerCase();
          const contentType =
            ext === ".mp4"
              ? "video/mp4"
              : ext === ".jsonl"
                ? "application/x-ndjson"
                : ext === ".json"
                  ? "application/json"
                  : "application/octet-stream";
          res.setHeader("Content-Type", contentType);
          res.setHeader("Content-Length", String(stat.size));
          fs.createReadStream(filePath).pipe(res);
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serveRepoData()],
  test: {
    globals: true,
    environment: "node",
  },
});
