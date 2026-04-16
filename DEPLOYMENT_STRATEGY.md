# LLMJury Workbench - Deployment Strategy

## Overview

This workbench is **self-contained**: evaluations run via subprocess or in-process calls to `runners/run_llmjury_evaluator.py` from the repository root (no external monorepo checkout required).

---

## Docker Deployment

### Multi-Stage Build

The workbench uses a multi-stage Dockerfile for optimization:

**Build Context:**
```bash
# Build from this repository root (directory containing Dockerfile and app.py)
cd llmjury_workbench
docker build -t llmjury-workbench .
```

**Benefits:**
- Reduced image size: ~600-800MB (vs 2-3GB single-stage)
- Faster deployments
- Smaller attack surface

---

## Kubernetes Deployment

### Deployment Configuration

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llmjury-workbench
spec:
  replicas: 2
  selector:
    matchLabels:
      app: llmjury-workbench
  template:
    metadata:
      labels:
        app: llmjury-workbench
    spec:
      containers:
      - name: workbench
        image: llmjury-workbench:latest
        ports:
        - containerPort: 8501
        resources:
          requests:
            memory: '1Gi'
            cpu: '500m'
          limits:
            memory: '2Gi'
            cpu: '1000m'
        env:
        - name: PYTHONPATH
          value: '/app'
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm-api-keys
              key: openai-key
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm-api-keys
              key: anthropic-key
        livenessProbe:
          httpGet:
            path: /_stcore/health
            port: 8501
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /_stcore/health
            port: 8501
          initialDelaySeconds: 10
          periodSeconds: 10
        volumeMounts:
        - name: evaluation-results
          mountPath: /app/temp_evaluations
      volumes:
      - name: evaluation-results
        persistentVolumeClaim:
          claimName: workbench-results-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: llmjury-workbench
spec:
  selector:
    app: llmjury-workbench
  ports:
  - port: 80
    targetPort: 8501
  type: LoadBalancer
```

### PersistentVolumeClaim

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: workbench-results-pvc
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Gi
```

---

## Environment Configuration

### Required Variables

```bash
OPENAI_API_KEY=sk-...           # Required for OpenAI models
ANTHROPIC_API_KEY=sk-ant-...    # Required for Anthropic models
PYTHONPATH=/app         # Required for imports
```

### Optional Variables

```bash
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
OUTPUT_DIR=/app/temp_evaluations
```

### Secrets Management

**Production:**
- Kubernetes: Use `Secret` resources
- AWS: Secrets Manager or Parameter Store
- Azure: Key Vault
- GCP: Secret Manager

---

## CI/CD Pipeline

### GitHub Actions

```yaml
name: Build and Deploy

on:
  push:
    branches: [ main ]
    paths:
      - 'llmjury_workbench/**'

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4

    - name: Build Docker Image
      run: |
        docker build -f llmjury_workbench/Dockerfile \
          -t ${{ secrets.REGISTRY }}/llmjury-workbench:${{ github.sha }} \
          -t ${{ secrets.REGISTRY }}/llmjury-workbench:latest .

    - name: Push to Registry
      run: |
        docker push ${{ secrets.REGISTRY }}/llmjury-workbench:${{ github.sha }}
        docker push ${{ secrets.REGISTRY }}/llmjury-workbench:latest

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
    - name: Deploy to Kubernetes
      run: |
        kubectl set image deployment/llmjury-workbench \
          workbench=${{ secrets.REGISTRY }}/llmjury-workbench:${{ github.sha }}
        kubectl rollout status deployment/llmjury-workbench
```

---

## Resource Requirements

| Environment | CPU | Memory | Storage |
|-------------|-----|--------|---------|
| Development | 1 core | 1GB | 5GB |
| Production (single) | 2 cores | 2GB | 10GB |
| Production (HA) | 2 cores/pod | 2GB/pod | Shared PV |

---

## Cloud Platforms

### AWS (ECS/Fargate)

```json
{
  "family": "llmjury-workbench",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/workbench-task-role",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/workbench-execution-role",
  "networkMode": "awsvpc",
  "containerDefinitions": [{
    "name": "workbench",
    "image": "llmjury-workbench:latest",
    "memory": 2048,
    "cpu": 1024,
    "portMappings": [{
      "containerPort": 8501,
      "protocol": "tcp"
    }],
    "environment": [{
      "name": "PYTHONPATH",
      "value": "/app"
    }],
    "secrets": [{
      "name": "OPENAI_API_KEY",
      "valueFrom": "arn:aws:secretsmanager:region:account:secret:openai-key"
    }],
    "mountPoints": [{
      "sourceVolume": "results",
      "containerPath": "/app/temp_evaluations"
    }]
  }],
  "volumes": [{
    "name": "results",
    "efsVolumeConfiguration": {
      "fileSystemId": "fs-xxxxx"
    }
  }]
}
```

### Google Cloud Run

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: llmjury-workbench
spec:
  template:
    spec:
      containers:
      - image: gcr.io/PROJECT_ID/llmjury-workbench
        ports:
        - containerPort: 8501
        env:
        - name: PYTHONPATH
          value: /app
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: openai-api-key
              key: key
        resources:
          limits:
            memory: 2Gi
            cpu: 2000m
```

### Azure Container Instances

```yaml
apiVersion: '2019-12-01'
location: eastus
name: llmjury-workbench
properties:
  containers:
  - name: workbench
    properties:
      image: llmjury-workbench:latest
      resources:
        requests:
          cpu: 2
          memoryInGb: 2
      ports:
      - port: 8501
      environmentVariables:
      - name: PYTHONPATH
        value: /app
      - name: OPENAI_API_KEY
        secureValue: <from-key-vault>
  osType: Linux
  ipAddress:
    type: Public
    ports:
    - protocol: tcp
      port: 8501
```

---

## Monitoring & Health

### Health Check Endpoint

```bash
GET http://localhost:8501/_stcore/health
```

Returns `200 OK` when healthy.

### Monitoring Metrics

- Pod/container resource usage (CPU, memory)
- Health check response times
- Evaluation success/failure rates
- API rate limits and errors
- Persistent volume disk usage

---

## Security Best Practices

1. **API Keys**: Use secrets management, never commit to code
2. **Network**: Restrict ingress to port 8501 only
3. **Container**: Run as non-root user where possible
4. **Dependencies**: Regularly update base images and packages
5. **Data**: Secure persistent volumes with appropriate access controls
6. **HTTPS**: Use TLS termination at load balancer/ingress
7. **RBAC**: Implement role-based access control in Kubernetes

---

## Troubleshooting

### Container Startup Issues
- Check `PYTHONPATH=/app` is set
- Verify API keys are available
- Review logs: `docker logs <container-id>`

### Health Check Failures
- Ensure port 8501 is exposed and accessible
- Verify Streamlit is running: `ps aux | grep streamlit`
- Check container resource limits

### Evaluation Errors
- Validate API keys are correct and active
- Confirm the image includes `llmjury`, `runners`, and `app.py` from this repository
- Review logs in `temp_evaluations/`

### Out of Memory
- Increase memory limits (minimum 2GB recommended)
- Monitor evaluation batch sizes
- Check for memory leaks in long-running sessions

---

## Upgrade Strategy

1. Build new image with updated version tag
2. Test in staging/dev environment
3. Deploy to production with rolling update
4. Monitor health checks and application logs
5. Rollback if issues detected (`kubectl rollout undo`)

---

## Recommended Production Setup

**Kubernetes deployment with:**
- 2+ replicas for high availability
- Persistent volume (ReadWriteMany) for evaluation results
- Kubernetes Secrets for API keys
- Liveness and readiness probes configured
- Resource limits and requests defined
- HTTPS/TLS termination at ingress/load balancer
- Monitoring and alerting configured
