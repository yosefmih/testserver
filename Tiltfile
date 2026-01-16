# Porter Hot Reload - Simple Version
# Hot reloads directly into your existing Porter deployment

# Use your current kubectl context (just like regular Tilt)
# Make sure you run: pctx local && pk config view --raw > ~/.kube/config
# before running tilt up

print("🚀 Porter Hot Reload for txx app")

# Load restart_process extension (modern replacement for restart_container)
load('ext://restart_process', 'docker_build_with_restart')

# Allow your Porter cluster context
allow_k8s_contexts('dev-cluster-2e6or1-user@dev-cluster-2e6or1')

# Use your Porter registry (credential helper handles auth)
default_registry('992382605253.dkr.ecr.us-east-1.amazonaws.com')

# Build configuration with manual control
docker_build_with_restart(
    '992382605253.dkr.ecr.us-east-1.amazonaws.com/txx',
    context='.',
    dockerfile='./Dockerfile',
    entrypoint=['python', 'server.py'],
    # Remove live_update for now - we'll use full rebuilds with manual triggers
    # This ensures consistent builds and avoids filesystem sync issues
)

# Load your existing Porter deployment so Tilt can manage it
k8s_yaml(local('kubectl get deployment txx-web -o yaml'))

# Configure the existing deployment for hot reload
k8s_resource(
    'txx-web',
    port_forwards=['13000:3000'],
    labels=['porter-hot-reload'],
    trigger_mode=TRIGGER_MODE_MANUAL  # Manual control - no auto-updates to prevent Porter conflicts
)

print("🎯 Hot reloading into existing Porter deployment!")
print("🌐 App will be available at: http://localhost:3000")
print("📝 Edit server.py and watch changes in ~2-3 seconds")