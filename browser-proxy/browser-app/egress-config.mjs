const browserFacingProxy = { name: "browser-egress", addr: "127.0.0.1:3128", listener: { type: "tcp" }, handler: { type: "http" } };
const config = { services: [browserFacingProxy] };

if (process.env.UPSTREAM_PROXY_URL) {
  const upstream = new URL(process.env.UPSTREAM_PROXY_URL);
  const dialerByScheme = { "http:": "tcp", "https:": "tls" };
  if (!dialerByScheme[upstream.protocol]) throw new Error(`UPSTREAM_PROXY_URL must be http:// or https://, got ${upstream.protocol}`);
  if (!upstream.port) throw new Error("UPSTREAM_PROXY_URL must include a port");

  browserFacingProxy.handler.chain = "upstream";
  config.chains = [{
    name: "upstream",
    hops: [{
      name: "upstream",
      nodes: [{
        name: "upstream",
        addr: `${upstream.hostname}:${upstream.port}`,
        connector: { type: "http", auth: { username: decodeURIComponent(upstream.username), password: decodeURIComponent(upstream.password) } },
        dialer: { type: dialerByScheme[upstream.protocol], tls: { serverName: upstream.hostname } },
      }],
    }],
  }];
}

process.stdout.write(JSON.stringify(config));
