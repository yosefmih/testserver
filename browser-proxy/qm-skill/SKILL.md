---
name: browser-service
description: Drive the organization's own browser service, a real Chrome whose traffic reaches websites from the organization's proxy IP, to act on sites (sign in, fill and submit forms, click through flows). Use it instead of the browse skill's hosted providers whenever a BROWSER_SERVICE_CDP_URL credential is available. Requires managed model access.
---

# Browser service

The organization runs its own browser as a Porter app. Websites see the organization's
proxy IP, not a datacenter IP. The proxy's credentials stay inside that app; you hold only
a URL that lets you drive the browser.

- Each task gets a fresh browser. Nothing is saved between tasks: no cookies, no sign-ins.
- Only pages loaded in this browser use the proxy IP. Your own shell (`curl`, `wget`) does not.

## Credential

`BROWSER_SERVICE_CDP_URL` is an org Service credential delivered as sandbox env. It is not
in your shell by default: name its handle in `credentials` on every `execute` that uses it.
It is a secret. Pass it only as an argument, never print it or write it to a file.

If no handle for it exists, this skill is unavailable here; say so.

## Run a task

Read the browse skill and use its runtime, its runner, and its rules on spending and
reporting (its section "2. Run the task with the embedded runner" and "Reporting"), with
`"$BROWSER_SERVICE_CDP_URL"` as the runner's CDP URL argument:

```bash
/opt/browser-engine/venv/bin/python /tmp/browse-runner.py "<task>" "$BROWSER_SERVICE_CDP_URL" \
  | tee /tmp/browse-out.txt
```

Skip the browse skill's provider, profile, live view and clean-up steps; none of them apply.
The browser closes by itself once the runner disconnects.

## Check the exit IP

When the person asks which IP websites see, or to confirm the browser works:

```bash
/opt/browser-engine/venv/bin/python - "$BROWSER_SERVICE_CDP_URL" <<'PY'
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(sys.argv[1])
    page = browser.contexts[0].new_page()
    page.goto("https://www.cloudflare.com/cdn-cgi/trace", timeout=60000)
    print("\n".join(l for l in page.inner_text("body").splitlines() if l.split("=")[0] in ("ip", "loc")))
    browser.close()
PY
```

## Outcomes

- `signin_needed`: this browser keeps no sign-ins and has no live view. Tell the person the
  site needs a sign-in this browser can't hold yet.
- Connection refused with `503`: every browser is in use. Wait a minute and retry once.
- Connection refused with `401`: the credential is wrong or was rotated. Tell an admin.
