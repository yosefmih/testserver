# 

import porter_sdk 

sandbox = porter_sdk.NewSandbox(
    image: "nginx:latest",
    name: "test-sandbox",
    env: {
        "PORTER_API_URL": "http://localhost:8080",
        "PORTER_API_TOKEN": "test",
    },
    mounts: [
        porter_sdk.Mount(
            source_path: "/tmp",
            path_in_sandbox: "/tmp",
            read: True,
            write: False, 
            execute: False,
        ),
    ],
    networking_config: porter_sdk.NetworkingConfig(
        port: 8080, # if not set, container will not be exposed at all
        private: True,
        public: False,
        egress_allowlist: ["0.0.0.0/0"], # egress not allowed by default, add IPs or CIDRs here to allow
        ingress_allowlist: ["0.0.0.0/0"], # ingress not allowed by default, add IPs or CIDRs here to allow
        domainNames: ["example.com"],
    ),
)

sandbox.UpadateNetworkingConfig(
    egress_allowlist: ["0.0.0.0/0"],
    ingress_allowlist: ["0.0.0.0/0"],
    domainNames: ["example.com"],
)

# < 1s latency
sandbox.Run();

# instantenous 
sandbox.WriteTo(path); 
sandbox.ReadFrom(path); 

sandbox.Destory();