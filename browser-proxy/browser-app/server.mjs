import { spawn } from "node:child_process";
import { timingSafeEqual } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const listenPort = Number(process.env.PORT ?? 8080);
const maxBrowsers = Number(process.env.MAX_BROWSERS ?? 2);
const idleCloseMs = Number(process.env.BROWSER_IDLE_CLOSE_SECONDS ?? 30) * 1000;
const browserToken = Buffer.from(requiredEnv("BROWSER_TOKEN"));
const display = ":99";
const chromiumFlags = [
  "--no-sandbox",
  "--disable-dev-shm-usage",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-background-networking",
  "--disable-component-update",
  "--disable-sync",
  "--disable-blink-features=AutomationControlled",
  "--disable-quic",
  "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
  "--proxy-server=http://127.0.0.1:3128",
  "--remote-debugging-port=0",
  "--window-size=1440,900",
  "--lang=en-US",
  "--password-store=basic",
];
const browsersBySession = new Map();

startVirtualDisplay();

const server = http.createServer((request, response) => {
  if (request.url === "/health") return response.writeHead(200).end("ok\n");
  response.writeHead(404).end();
});
server.on("upgrade", (request, client, head) => {
  connectClient(request, client, head).catch((error) => {
    console.error(`connection failed: ${error.message}`);
    rejectUpgrade(client, 502, "Bad Gateway");
  });
});
server.listen(listenPort, () => console.log(`browser service listening on :${listenPort}, up to ${maxBrowsers} browsers`));

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, async () => {
    server.close();
    await Promise.all([...browsersBySession.values()].map(closeBrowser));
    process.exit(0);
  });
}

async function connectClient(request, client, head) {
  client.on("error", () => client.destroy());
  const url = new URL(request.url, "http://browser-service");
  if (!hasBrowserToken(request, url)) return rejectUpgrade(client, 401, "Unauthorized");
  const websocketKey = request.headers["sec-websocket-key"];
  if (!websocketKey) return rejectUpgrade(client, 400, "Bad Request");

  const browser = browserForSession(url.pathname);
  if (!browser) return rejectUpgrade(client, 503, "Service Unavailable");
  browser.clients.add(client);
  clearTimeout(browser.idleTimer);
  client.once("close", () => releaseClient(browser, client));

  const { devtools } = await browser.ready;
  const upstream = net.connect(devtools.port, "127.0.0.1");
  upstream.once("connect", () => {
    upstream.write(
      `GET ${devtools.path} HTTP/1.1\r\n` +
        `Host: 127.0.0.1:${devtools.port}\r\n` +
        "Upgrade: websocket\r\nConnection: Upgrade\r\n" +
        `Sec-WebSocket-Key: ${websocketKey}\r\nSec-WebSocket-Version: 13\r\n\r\n`,
    );
    if (head.length) upstream.write(head);
    upstream.pipe(client);
    client.pipe(upstream);
  });
  upstream.on("error", () => client.destroy());
  upstream.once("close", () => client.destroy());
  client.once("close", () => upstream.destroy());
  console.log(`session ${browser.session}: client connected (${browser.clients.size} open)`);
}

function browserForSession(session) {
  const existing = browsersBySession.get(session);
  if (existing) return existing;
  if (browsersBySession.size >= maxBrowsers) return undefined;

  const browser = { session, clients: new Set(), idleTimer: undefined };
  browser.ready = launchChromium(browser);
  browser.ready.catch(() => closeBrowser(browser));
  browsersBySession.set(session, browser);
  return browser;
}

function releaseClient(browser, client) {
  browser.clients.delete(client);
  console.log(`session ${browser.session}: client disconnected (${browser.clients.size} open)`);
  if (browser.clients.size === 0) browser.idleTimer = setTimeout(() => closeBrowser(browser), idleCloseMs);
}

async function launchChromium(browser) {
  const profileDir = await mkdtemp(path.join(os.tmpdir(), "chromium-"));
  const chromium = spawn("chromium", [...chromiumFlags, `--user-data-dir=${profileDir}`, "about:blank"], {
    detached: true,
    env: {
      PATH: process.env.PATH,
      HOME: profileDir,
      DISPLAY: display,
      TZ: process.env.BROWSER_TIMEZONE ?? "UTC",
      LANG: "en_US.UTF-8",
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  let stderrTail = "";
  chromium.stderr.on("data", (chunk) => (stderrTail = (stderrTail + chunk).slice(-4000)));
  const exited = new Promise((resolve) => chromium.once("exit", resolve));
  exited.then(() => closeBrowser(browser));
  Object.assign(browser, { chromium, profileDir, exited });
  console.log(`session ${browser.session}: launching chromium (pid ${chromium.pid})`);

  const devtools = await waitForDevTools(profileDir, chromium).catch((error) => {
    throw new Error(`${error.message}\n${stderrTail}`);
  });
  return { devtools };
}

async function waitForDevTools(profileDir, chromium) {
  for (let attempt = 0; attempt < 300; attempt++) {
    if (chromium.exitCode !== null || chromium.signalCode !== null) throw new Error("chromium exited during startup");
    const activePort = await readFile(path.join(profileDir, "DevToolsActivePort"), "utf8").catch(() => "");
    const [port, browserPath] = activePort.split("\n");
    if (port && browserPath) return { port: Number(port), path: browserPath };
    await sleep(100);
  }
  throw new Error("chromium did not open its DevTools port within 30s");
}

async function closeBrowser(browser) {
  if (browser.closing) return browser.closing;
  browser.closing = (async () => {
    clearTimeout(browser.idleTimer);
    browsersBySession.delete(browser.session);
    for (const client of browser.clients) client.destroy();
    if (browser.chromium) {
      killProcessGroup(browser.chromium, "SIGTERM");
      const forceKill = setTimeout(() => killProcessGroup(browser.chromium, "SIGKILL"), 5000);
      await browser.exited;
      clearTimeout(forceKill);
      await rm(browser.profileDir, { recursive: true, force: true });
    }
    console.log(`session ${browser.session}: browser closed`);
  })();
  return browser.closing;
}

function killProcessGroup(child, signal) {
  try {
    process.kill(-child.pid, signal);
  } catch {}
}

function hasBrowserToken(request, url) {
  const bearer = request.headers.authorization?.replace(/^Bearer /, "");
  const presented = Buffer.from(url.searchParams.get("token") ?? bearer ?? "");
  return presented.length === browserToken.length && timingSafeEqual(presented, browserToken);
}

function rejectUpgrade(client, status, reason) {
  client.end(`HTTP/1.1 ${status} ${reason}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);
}

function startVirtualDisplay() {
  const xvfb = spawn("Xvfb", [display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"], { stdio: "ignore" });
  xvfb.once("exit", (code, signal) => {
    console.error(`Xvfb exited (${signal ?? code}); stopping`);
    process.exit(1);
  });
}

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}
