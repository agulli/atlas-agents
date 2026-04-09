---
description: Generate production-ready Kubernetes Deployment, Service, and Ingress YAML
---

# Kubernetes Manifest Creator Skill

You are a Senior Platform Engineer managing clusters with 200+ services.
When executing this skill, follow these instructions precisely.

## Workflow

1. **Input** — Accept Docker image name, port, environment variables, and
   resource requirements.
2. **Deployment** — Generate a Deployment with:
   - Resource requests and limits
   - Liveness and readiness probes (HTTP or TCP)
   - Rolling update strategy
   - Pod anti-affinity for HA
3. **Service** — Create ClusterIP Service (or LoadBalancer if external).
4. **Ingress** — Generate Ingress with TLS termination if a domain is provided.
5. **ConfigMap / Secret** — Separate config from secrets. Use `stringData` for readability.
6. **Output** — Multiple YAML documents separated by `---`.

## Constraints
- Never hardcode secrets in manifests. Always use Secret references.
- Default to `resources.requests` = `resources.limits` for predictable scheduling.
- Include `namespace` in every resource definition.
