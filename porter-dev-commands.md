# Porter CLI Hot Reload Integration

## Proposed CLI Commands

```bash
# Initialize hot reload for an app
porter dev init [app-name]
  --cluster-id <id>     # Optional: specify cluster 
  --project-id <id>     # Optional: specify project
  --output-dir <path>   # Where to generate Tiltfile (default: current dir)
  --mode <safe|direct>  # safe: separate dev deployment, direct: modify existing

# Start hot reload development
porter dev start [app-name]
  # Equivalent to: tilt up in the generated directory

# Stop hot reload
porter dev stop [app-name]  
  # Equivalent to: tilt down

# Show hot reload status
porter dev status [app-name]
  # Shows running Tilt processes and their status

# Generate credentials for external tools
porter dev kubeconfig [app-name]
  # Outputs kubeconfig for use with kubectl/tilt
  
porter dev registry-auth [app-name]
  # Ensures Docker credential helper is configured
```

## Implementation in Porter CLI

### porter dev init
- Fetches app configuration from Porter API
- Generates Tiltfile based on app's build config  
- Sets up kubeconfig with proper context
- Validates credential helper configuration
- Creates development namespace if using safe mode

### porter dev start
- Validates Tiltfile exists
- Runs `tilt up` in the app directory
- Opens Tilt UI in browser
- Shows initial status and instructions

## Generated Tiltfile Features

### Smart Build Detection
```python
# Detects app framework and sets appropriate live update rules
if build_method == "docker":
    # Use Dockerfile with live updates
elif build_method == "pack":
    # Use buildpack detection for live updates
```

### Environment Integration
```python
# Injects Porter environment variables
env_vars = porter_client.get_app_env(app_name)
# Applies them to development deployment
```

### Multi-Service Support
```python
# For apps with multiple services
for service in porter_app.services:
    docker_build(f"{registry}/{service.name}", service.build_context)
```

## Configuration File (.porter-dev.yaml)

```yaml
# Generated per-app development configuration
app: txx
project_id: 1  
cluster_id: 1
registry: 992382605253.dkr.ecr.us-east-1.amazonaws.com
kubeconfig_context: dev-cluster-2e6or1-user@dev-cluster-2e6or1
mode: safe  # or "direct"

hot_reload:
  enabled: true
  sync_patterns:
    - "*.py"
    - "*.js" 
    - "*.html"
  rebuild_patterns:
    - "requirements.txt"
    - "package.json"
    - "Dockerfile"
    
services:
  - name: web
    port: 3000
    command: ["python", "server.py"]
```