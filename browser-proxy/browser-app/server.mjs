import { spawn } from "node:child_process";
import { timingSafeEqual } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { chromium as playwright } from "playwright-core";

const listenPort = Number(process.env.PORT ?? 8080);
const maxBrowsers = Number(process.env.MAX_BROWSERS ?? 2);
const idleCloseMs = Number(process.env.BROWSER_IDLE_CLOSE_SECONDS ?? 300) * 1000;
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
const pageActions = { goto, text, snapshot, screenshot, click, fill, press, eval: evaluate };
const browsersBySession = new Map();

startVirtualDisplay();

const server = http.createServer((request, response) => {
  handleHttpRequest(request, response).catch((error) => sendJson(response, 500, { error: error.message }));
});
server.on("upgrade", (request, client, head) => {
  connectDevToolsClient(request, client, head).catch((error) => {
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

async function handleHttpRequest(request, response) {
  const url = new URL(request.url, "http://browser-service");
  if (url.pathname === "/health") return sendText(response, 200, "ok\n");
  if (!hasBrowserToken(request, url)) return sendJson(response, 401, { error: "missing or wrong token" });

  const [, resource, sessionName, actionName] = url.pathname.split("/");
  if (resource !== "sessions" || !sessionName) return sendJson(response, 404, { error: "use /sessions/<name>/<action>" });
  const session = `/${sessionName}`;

  if (request.method === "DELETE" && !actionName) {
    const browser = browsersBySession.get(session);
    if (browser) await closeBrowser(browser);
    return sendJson(response, 200, { closed: Boolean(browser) });
  }

  const action = pageActions[actionName];
  if (!action) return sendJson(response, 404, { error: `unknown action; use one of: ${Object.keys(pageActions).join(", ")}` });
  const params = { ...Object.fromEntries(url.searchParams), ...(await readParams(request)) };
  delete params.token;

  const browser = browserForSession(session);
  if (!browser) return sendJson(response, 503, { error: `all ${maxBrowsers} browsers are in use` });
  try {
    const result = await runInSession(browser, (page) => action(page, params));
    response.writeHead(result.status, { "content-type": result.contentType }).end(result.body);
  } catch (error) {
    const message = error.message.split("\n")[0];
    sendJson(response, message.includes("net::ERR_") ? 502 : 422, { error: message });
  }
}

async function goto(page, { url }) {
  if (!url) throw new Error("url is required");
  const response = await page.goto(url, { waitUntil: "load", timeout: 60000 });
  return json({ url: page.url(), status: response?.status() ?? null, title: await page.title() });
}

async function text(page) {
  return plain(`${page.url()}\n\n${await page.locator("body").innerText()}`);
}

async function snapshot(page) {
  return plain(`${page.url()}\n\n${await page.locator("body").ariaSnapshot()}`);
}

async function screenshot(page, { full }) {
  return { status: 200, contentType: "image/png", body: await page.screenshot({ fullPage: full === "true" }) };
}

async function click(page, { selector }) {
  if (!selector) throw new Error("selector is required");
  await page.locator(selector).first().click({ timeout: 15000 });
  return pageStateAfterAction(page);
}

async function fill(page, { selector, text: value }) {
  if (!selector) throw new Error("selector is required");
  await page.locator(selector).first().fill(value ?? "", { timeout: 15000 });
  return pageStateAfterAction(page);
}

async function press(page, { key }) {
  if (!key) throw new Error("key is required");
  await page.keyboard.press(key);
  return pageStateAfterAction(page);
}

async function evaluate(page, { script }) {
  if (!script) throw new Error("script is required");
  return json({ value: await page.evaluate(script) });
}

async function pageStateAfterAction(page) {
  await sleep(500);
  await page.waitForLoadState("load", { timeout: 15000 }).catch(() => {});
  return json({ url: page.url(), title: await page.title() });
}

async function runInSession(browser, run) {
  clearTimeout(browser.idleTimer);
  browser.queue = (browser.queue ?? Promise.resolve()).catch(() => {}).then(async () => run(await activePage(browser)));
  try {
    return await browser.queue;
  } finally {
    if (browser.clients.size === 0) scheduleIdleClose(browser);
  }
}

async function activePage(browser) {
  const { devtools } = await browser.ready;
  browser.automation ??= playwright.connectOverCDP(`ws://127.0.0.1:${devtools.port}${devtools.path}`);
  const automation = await browser.automation.catch((error) => {
    browser.automation = undefined;
    throw error;
  });
  const context = automation.contexts()[0];
  return context.pages().at(-1) ?? (await context.newPage());
}

async function connectDevToolsClient(request, client, head) {
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
  console.log(`session ${browser.session}: devtools client connected (${browser.clients.size} open)`);
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
  console.log(`session ${browser.session}: devtools client disconnected (${browser.clients.size} open)`);
  if (browser.clients.size === 0) scheduleIdleClose(browser);
}

function scheduleIdleClose(browser) {
  clearTimeout(browser.idleTimer);
  browser.idleTimer = setTimeout(() => closeBrowser(browser), idleCloseMs);
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
    await browser.automation?.then((automation) => automation.close()).catch(() => {});
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
  const presented = Buffer.from(presentedToken(request, url));
  return presented.length === browserToken.length && timingSafeEqual(presented, browserToken);
}

function presentedToken(request, url) {
  const [scheme, credentials = ""] = (request.headers.authorization ?? "").split(" ");
  if (scheme === "Bearer") return credentials;
  if (scheme === "Basic") return Buffer.from(credentials, "base64").toString().split(":").slice(1).join(":");
  return url.searchParams.get("token") ?? "";
}

async function readParams(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 1024 * 1024) throw new Error("request body over 1 MB");
    chunks.push(chunk);
  }
  const body = Buffer.concat(chunks).toString();
  if (!body) return {};
  if (request.headers["content-type"]?.startsWith("application/json")) return JSON.parse(body);
  return Object.fromEntries(new URLSearchParams(body));
}

function json(value) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(value) };
}

function plain(body) {
  return { status: 200, contentType: "text/plain; charset=utf-8", body };
}

function sendJson(response, status, value) {
  response.writeHead(status, { "content-type": "application/json" }).end(JSON.stringify(value));
}

function sendText(response, status, body) {
  response.writeHead(status, { "content-type": "text/plain" }).end(body);
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
