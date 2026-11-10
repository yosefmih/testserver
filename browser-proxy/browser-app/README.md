# browser-app

A real Chrome that agents drive over CDP (the Chrome DevTools Protocol), deployable as a
Porter app. All of the browser's traffic leaves through an upstream proxy, such as Oxylabs
or Bright Data, whose credentials are env vars on this app only. The agents that drive the
browser never see them.

```
agent (QM sandbox) ──wss + token──▶ server.mjs ──CDP──▶ Chromium (headed, Xvfb)
                                                           │ --proxy-server
                                                           ▼
                                              gost on 127.0.0.1:3128 ──▶ upstream proxy ──▶ website
```

- `server.mjs` checks the token and starts one Chromium per URL path. It closes that
  browser 30 seconds after the last client disconnects and deletes its profile.
- gost and Chromium run as different users. Only gost can read the upstream credentials,
  so a page or the agent driving the browser can't reach them. Chromium also blocks
  `file://`.
- gost logs every site the browser connects to.

## Deploy as a Porter app

- Repo `yosefmih/testserver`, Dockerfile `browser-proxy/browser-app/Dockerfile`, build
  context `browser-proxy/browser-app`.
- One web service: port `8080`, health check `/health`, a public domain, 1 instance.
  Browsers live in the pod, so more instances would split sessions. 2 vCPU and 4 GB fit
  the default of 2 browsers.
- Env vars, all secret:
  - `BROWSER_TOKEN`: required. Any long random string, e.g. `openssl rand -hex 32`.
  - `UPSTREAM_PROXY_URL`: `http://` or `https://` proxy URL with credentials. Without it
    the browser goes direct. For Oxylabs residential, one sticky session per agent, with
    the password URL-encoded:
    `https://customer-<user>-cc-US-st-us_new_york-sessid-<agent>-sesstime-1440:<password>@pr.oxylabs.io:7777`
  - `BROWSER_TIMEZONE`: match the proxy IP's location, e.g. `America/New_York` for
    `st-us_new_york`. Defaults to `UTC`.
  - Optional: `MAX_BROWSERS` (default 2), `BROWSER_IDLE_CLOSE_SECONDS` (default 30).

## Connect

`wss://<app domain>/?token=<BROWSER_TOKEN>` is a CDP endpoint for Playwright's
`connect_over_cdp`, browser-use's `BrowserSession(cdp_url=…)`, or Puppeteer's `connect`.
A different path, such as `/task-42?token=…`, gets a separate browser.

## Use it from QM

1. In QM's admin, add a Service credential, env `BROWSER_SERVICE_CDP_URL`, delivery
   "Sandbox env", value `wss://<app domain>/?token=<BROWSER_TOKEN>`.
2. Add the skill in `../qm-skill/SKILL.md`, for example by asking QM to save it as a skill,
   then share it org-wide as an org admin.
3. Ask QM which IP websites see through the browser service. It should report the proxy IP.

## Tested

Locally (Docker on arm64), against Oxylabs residential with a sticky New York session:

- Playwright and browser-use 0.12.9 both connected through one WebSocket and loaded pages.
- Exit IP was a Verizon residential IP in New York, the same across requests. Cloudflare's
  trace showed it too.
- Headed Chrome 156, `navigator.webdriver` false, timezone `America/New_York`.
- A wrong token got `401`. `file://` was blocked.
- As the browser's user, the gost config and the gost and PID 1 environments were
  unreadable. No browser-side process had the upstream URL in its environment.

Not tested yet: running it as a Porter app, and QM driving it. The app needs outbound
access to the upstream proxy's port (`7777` for Oxylabs). If pages time out and gost logs
failed dials to the proxy, the cluster is blocking that port.
