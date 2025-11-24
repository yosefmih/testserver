# EKS Deployment Guide with Pod Identity

This guide shows how to deploy the Amharic Scraper Service on Amazon EKS using Pod Identity for secure S3 access.

## Overview

EKS Pod Identity allows your pods to assume IAM roles without storing AWS credentials. The service will automatically use the pod's IAM role to access S3.

## Prerequisites

- Amazon EKS cluster (v1.24+)
- `kubectl` configured to access your cluster
- `aws` CLI installed and configured
- S3 bucket created

## Step 1: Create IAM Policy

Create an IAM policy that grants S3 access:

```bash
cat > scraper-s3-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME"
    }
  ]
}
EOF

# Create the policy
aws iam create-policy \
  --policy-name AmharicScraperS3Policy \
  --policy-document file://scraper-s3-policy.json
```

Note the policy ARN from the output.

## Step 2: Create IAM Role with EKS Pod Identity

### Option A: Using EKS Pod Identity (Recommended for EKS 1.24+)

```bash
# Get your cluster's OIDC provider
CLUSTER_NAME=your-cluster-name
OIDC_PROVIDER=$(aws eks describe-cluster --name $CLUSTER_NAME --query "cluster.identity.oidc.issuer" --output text | sed -e "s/^https:\/\///")

# Create IAM role
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR-ACCOUNT-ID:oidc-provider/$OIDC_PROVIDER"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "$OIDC_PROVIDER:sub": "system:serviceaccount:default:amharic-scraper",
          "$OIDC_PROVIDER:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name AmharicScraperRole \
  --assume-role-policy-document file://trust-policy.json

# Attach policy to role
aws iam attach-role-policy \
  --role-name AmharicScraperRole \
  --policy-arn arn:aws:iam::YOUR-ACCOUNT-ID:policy/AmharicScraperS3Policy
```

### Option B: Using IRSA (IAM Roles for Service Accounts)

```bash
# Enable IRSA on your cluster if not already enabled
eksctl utils associate-iam-oidc-provider --cluster=$CLUSTER_NAME --approve

# Create service account with IAM role
eksctl create iamserviceaccount \
  --name amharic-scraper \
  --namespace default \
  --cluster $CLUSTER_NAME \
  --role-name AmharicScraperRole \
  --attach-policy-arn arn:aws:iam::YOUR-ACCOUNT-ID:policy/AmharicScraperS3Policy \
  --approve
```

## Step 3: Create Kubernetes ConfigMap

Create a ConfigMap for non-sensitive configuration:

```yaml
# scraper-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: scraper-config
  namespace: default
data:
  AWS_REGION: "us-east-1"
  S3_BUCKET: "your-bucket-name"
  S3_METADATA_KEY: "scraper-metadata/jobs.json"
  S3_DATA_PREFIX: "scraper-data"
  SERVER_HOST: "0.0.0.0"
  SERVER_PORT: "8080"
  MAX_CONCURRENT_JOBS: "3"
  WORKER_THREADS: "5"
  DEFAULT_RATE_LIMIT: "2.0"
  DEFAULT_TIMEOUT: "10"
  DEFAULT_MAX_DEPTH: "3"
  DEFAULT_MAX_PAGES: "1000"
  DEFAULT_AMHARIC_THRESHOLD: "0.3"
```

Apply the ConfigMap:
```bash
kubectl apply -f scraper-config.yaml
```

## Step 4: Create Kubernetes Service Account

```yaml
# service-account.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: amharic-scraper
  namespace: default
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::YOUR-ACCOUNT-ID:role/AmharicScraperRole
```

Apply:
```bash
kubectl apply -f service-account.yaml
```

## Step 5: Create Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: amharic-scraper
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: amharic-scraper
  template:
    metadata:
      labels:
        app: amharic-scraper
    spec:
      serviceAccountName: amharic-scraper
      containers:
      - name: scraper
        image: your-registry/amharic-scraper:latest
        ports:
        - containerPort: 8080
          name: http
        envFrom:
        - configMapRef:
            name: scraper-config
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
```

Apply:
```bash
kubectl apply -f deployment.yaml
```

## Step 6: Create Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: amharic-scraper
  namespace: default
spec:
  selector:
    app: amharic-scraper
  ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
  type: ClusterIP
```

Apply:
```bash
kubectl apply -f service.yaml
```

## Step 7: Expose via Ingress (Optional)

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: amharic-scraper
  namespace: default
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
spec:
  rules:
  - host: scraper.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: amharic-scraper
            port:
              number: 80
```

Apply:
```bash
kubectl apply -f ingress.yaml
```

## Step 8: Build and Push Docker Image

Create a `Dockerfile` in the scraper directory:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Run server
CMD ["python", "server.py"]
```

Build and push:
```bash
cd testserver/scraper

# Build
docker build -t your-registry/amharic-scraper:latest .

# Push
docker push your-registry/amharic-scraper:latest
```

## Verification

### 1. Check Pod Status
```bash
kubectl get pods -l app=amharic-scraper
kubectl logs -l app=amharic-scraper
```

You should see:
```
Using IAM role for S3 access (EKS Pod Identity)
Server initialized successfully
Starting server on 0.0.0.0:8080
```

### 2. Test API from Within Cluster
```bash
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://amharic-scraper/health
```

Expected output:
```json
{
  "status": "healthy",
  "active_jobs": 0
}
```

### 3. Create Test Job
```bash
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl -X POST http://amharic-scraper/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "seed_urls": ["https://en.wikipedia.org/wiki/Amharic"],
    "config": {"max_pages": 10}
  }'
```

### 4. Verify S3 Access
Check your S3 bucket for the metadata file:
```bash
aws s3 ls s3://your-bucket-name/scraper-metadata/
aws s3 cp s3://your-bucket-name/scraper-metadata/jobs.json - | jq
```

## Scaling

### Horizontal Scaling
```bash
# Scale to 3 replicas
kubectl scale deployment amharic-scraper --replicas=3

# Or use HPA
kubectl autoscale deployment amharic-scraper \
  --cpu-percent=70 \
  --min=1 \
  --max=5
```

### Vertical Scaling
Update resource limits in deployment.yaml:
```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

## Monitoring

### View Logs
```bash
# All pods
kubectl logs -l app=amharic-scraper --tail=100 -f

# Specific pod
kubectl logs amharic-scraper-xxx-yyy --tail=100 -f
```

### Check Metrics
```bash
kubectl top pods -l app=amharic-scraper
```

### Access Metrics Endpoint (if implemented)
```bash
kubectl port-forward svc/amharic-scraper 8080:80
curl http://localhost:8080/metrics
```

## Troubleshooting

### Pod Cannot Access S3

1. **Check IAM role annotation:**
```bash
kubectl describe sa amharic-scraper | grep Annotations
```

Should show:
```
eks.amazonaws.com/role-arn: arn:aws:iam::xxx:role/AmharicScraperRole
```

2. **Check pod environment:**
```bash
kubectl exec -it amharic-scraper-xxx-yyy -- env | grep AWS
```

Should show:
```
AWS_ROLE_ARN=arn:aws:iam::xxx:role/AmharicScraperRole
AWS_WEB_IDENTITY_TOKEN_FILE=/var/run/secrets/eks.amazonaws.com/serviceaccount/token
```

3. **Test S3 access from pod:**
```bash
kubectl exec -it amharic-scraper-xxx-yyy -- python -c "
import boto3
s3 = boto3.client('s3', region_name='us-east-1')
print(s3.list_buckets())
"
```

### Pod Crashlooping

Check logs:
```bash
kubectl logs amharic-scraper-xxx-yyy --previous
```

Common issues:
- Missing S3_BUCKET config
- IAM role not properly attached
- Network policies blocking S3 access

### Jobs Not Processing

1. Check pod logs for errors
2. Verify S3 metadata file exists and is accessible
3. Check worker pool status via API
4. Ensure sufficient resources (CPU/Memory)

## Security Best Practices

1. **Network Policies**: Restrict pod network access
2. **Resource Limits**: Set appropriate CPU/memory limits
3. **Read-Only Root**: Use read-only root filesystem
4. **Non-Root User**: Run as non-root user
5. **Image Scanning**: Scan Docker images for vulnerabilities

Example security context:
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  capabilities:
    drop:
    - ALL
```

## Production Checklist

- [ ] IAM role created with minimal S3 permissions
- [ ] Service account annotated with IAM role ARN
- [ ] ConfigMap created with all settings
- [ ] Resource limits configured
- [ ] Liveness and readiness probes configured
- [ ] Ingress/Load balancer configured
- [ ] Monitoring and logging set up
- [ ] Backup strategy for S3 metadata
- [ ] Alerting configured for failures
- [ ] Documentation updated with deployment info

## Cost Optimization

1. **Use Spot Instances**: For non-critical workloads
2. **Right-size Resources**: Monitor actual usage
3. **S3 Lifecycle Policies**: Archive old scraped content
4. **Cluster Autoscaler**: Scale nodes based on demand
5. **Reserved Capacity**: For predictable workloads

## Additional Resources

- [EKS Pod Identity Documentation](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [IAM Roles for Service Accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [Boto3 Credentials](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html)

