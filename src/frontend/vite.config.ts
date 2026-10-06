import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Hostnames the dev server will answer to, beyond localhost. Vite rejects any other
// Host header with "Blocked request" (DNS-rebinding protection), which breaks reaching
// the dev server through a tunnel or reverse proxy. Set e.g.
// VITE_ALLOWED_HOSTS=example.cloudfront.net when serving through one. Left unset in
// normal local use, so the default protection stays on.
const allowedHosts = process.env.VITE_ALLOWED_HOSTS
  ?.split(",")
  .map((host) => host.trim())
  .filter(Boolean);

// Path prefix the app is served under. "/" for normal local use; set e.g.
// VITE_BASE_PATH=/proxy/5173/ when a reverse proxy mounts the dev server under a
// sub-path, so generated asset URLs keep the prefix instead of pointing at the host
// root. `src/api.ts` reads the same value via import.meta.env.BASE_URL.
const base = process.env.VITE_BASE_PATH || "/";
const prefix = base.replace(/\/$/, "");

const BACKEND = "http://localhost:8000";

// Proxy both the bare and the prefixed form: whether a request arrives as /api/... or
// /proxy/5173/api/... depends on whether the upstream proxy strips the prefix before
// forwarding, which we cannot control from here. The prefixed rule strips it so the
// backend always sees /api/....
const proxy: Record<string, object> = {
  "/api": { target: BACKEND, changeOrigin: true },
};
if (prefix) {
  proxy[`${prefix}/api`] = {
    target: BACKEND,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(prefix, ""),
  };
}

// Re-attach the prefix to incoming request paths when the upstream proxy strips it.
//
// `base` does two jobs at once: it decides what URLs the generated HTML/JS point at,
// *and* the path the dev server answers on. Behind a prefix-stripping proxy those two
// need different values — the browser must ask for /proxy/5173/src/main.tsx (or the
// proxy cannot route it to this port), but the dev server receives /src/main.tsx. With
// `base` set, Vite 404s that, and a bare "/" triggers Vite's redirect-to-base, which the
// proxy prefixes a second time (/proxy/5173/proxy/5173/ — a white screen).
//
// This middleware runs ahead of Vite's own stack and restores the prefix, so Vite always
// sees prefixed paths regardless of what the proxy did. If the proxy *keeps* the prefix
// the condition is false and this is a no-op, so one config covers both kinds of proxy.
const restorePrefix = {
  name: "restore-proxy-prefix",
  configureServer(server: { middlewares: { use: (fn: unknown) => void } }) {
    if (!prefix) return;
    server.middlewares.use(
      (req: { url?: string }, _res: unknown, next: () => void) => {
        if (req.url && !req.url.startsWith(`${prefix}/`) && req.url !== prefix) {
          req.url = `${prefix}${req.url}`;
        }
        next();
      },
    );
  },
};

export default defineConfig({
  plugins: [react(), restorePrefix],
  base,
  server: {
    port: 5173,
    ...(allowedHosts?.length ? { allowedHosts } : {}),
    // Through an HTTPS reverse proxy the HMR socket must be told to use wss on the
    // public port; without this it tries ws on 5173 and only logs console noise.
    ...(process.env.VITE_HMR_CLIENT_PORT
      ? {
          hmr: {
            protocol: "wss",
            clientPort: Number(process.env.VITE_HMR_CLIENT_PORT),
          },
        }
      : {}),
    proxy,
  },
});
