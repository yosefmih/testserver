# browser-app

A real Chrome that agents drive over plain HTTPS (curl) or over CDP (the Chrome DevTools
Protocol), deployable as a Porter app. All of the browser's traffic leaves through an
upstream proxy, such as Oxylabs or Bright Data, whose credentials are env vars on this
app only. The agents that drive the browser never see them.

```
agent (QM sandbox) ──https + token──▶ server.mjs ──▶ Chromium (headed, Xvfb)
                                                       │ --proxy-server
                                                       ▼
                                          gost on 127.0.0.1:3128 ──▶ upstream proxy ──▶ website
```

- `server.mjs` checks the token and starts one Chromium per session. It closes a browser
  after 5 minutes without calls or connections, and deletes its profile.
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
- The cluster must allow outbound connections to the upstream proxy's port (`7777` for
  Oxylabs). If pages fail with `ERR_TUNNEL_CONNECTION_FAILED` and gost logs dial timeouts
  to the proxy, the cluster is blocking that port.
- Env vars, all secret:
  - `BROWSER_TOKEN`: required. Any long random string, e.g. `openssl rand -hex 32`.
  - `UPSTREAM_PROXY_URL`: `http://` or `https://` proxy URL with credentials. Without it
    the browser goes direct. For Oxylabs residential, one sticky session per agent, with
    the password URL-encoded:
    `https://customer-<user>-cc-US-st-us_new_york-sessid-<agent>-sesstime-1440:<password>@pr.oxylabs.io:7777`
  - `BROWSER_TIMEZONE`: match the proxy IP's location, e.g. `America/New_York` for
    `st-us_new_york`. Defaults to `UTC`.
  - Optional: `MAX_BROWSERS` (default 2), `BROWSER_IDLE_CLOSE_SECONDS` (default 300).

## Drive it

The token goes in `Authorization: Bearer <token>`, as the password of HTTP basic auth, or
as `?token=`. With basic auth in the URL, curl needs nothing else:

```bash
s="https://agent:<token>@<app domain>/sessions/my-task"
curl -sS --fail-with-body "$s/goto" --data-urlencode "url=https://www.cloudflare.com/cdn-cgi/trace"
curl -sS --fail-with-body "$s/text"
curl -sS -X DELETE "$s"
```

Actions under `/sessions/<name>/`, with parameters as form fields, JSON or query string:

- `goto` (`url`): open a page; returns the final URL, status and title.
- `snapshot`: the page's elements by role and name. `text`: its visible text.
- `screenshot` (`full=true` for the whole page): PNG.
- `click` (`selector`), `fill` (`selector`, `text`), `press` (`key`): return the URL and
  title once the page settles. Selectors are Playwright selectors, such as
  `role=button[name="Sign in"]`.
- `eval` (`script`): run JavaScript in the page; returns `{"value": …}`.
- `DELETE /sessions/<name>`: close the browser.

Errors are JSON `{"error": …}`: `401` bad token, `503` all browsers busy, `422` the action
failed, `502` the page could not be loaded through the proxy.

CDP clients (Playwright's `connect_over_cdp`, browser-use, Puppeteer) can connect to
`wss://<app domain>/<name>?token=<token>`. That reaches the same browser as
`/sessions/<name>/`.

## Use it from QM

1. In QM's admin, add an org Service credential, env `BROWSER_SERVICE_URL`, delivery
   "Sandbox env", value `https://agent:<BROWSER_TOKEN>@<app domain>`.
2. Import or add the skill in `../qm-skill/SKILL.md`. It drives the browser with
   Playwright over CDP, a 13 MB client install with no browser download, and uses curl
   for quick calls.
3. Ask QM which IP websites see through the browser service. It should report the proxy IP.

## Tested

Locally (Docker on arm64), against Oxylabs residential with a sticky New York session:

- Every HTTP action with curl: open, snapshot, text, fill, click, eval, screenshot,
  delete. A form filled through the API arrived at httpbin from the Oxylabs exit IP, with
  quotes in the value intact.
- Playwright and browser-use 0.12.9 over CDP.
- The exit IP was residential in New York, the same across requests and the same in
  Cloudflare's trace. Headed Chrome 156, `navigator.webdriver` false, timezone
  `America/New_York`.
- A wrong token got `401`. `file://` was blocked.
- As the browser's user, the gost config and the gost and PID 1 environments were
  unreadable. No browser-side process had the upstream URL in its environment.
