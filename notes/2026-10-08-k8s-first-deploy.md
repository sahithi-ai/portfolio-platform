# 2026-10-08 — cloud-sentinel on Kubernetes (local), Deployments

Streak restarted at 1 (no commit Oct 7). First commit `ad279c5` at 5:15, before the work.
Build weak-list: empty.

## What shipped
cloud-sentinel running as a 3-replica Deployment on Docker Desktop Kubernetes, credentials from a Secret holding only the read-only user, `/findings` returning real results through a port-forward. Four days after the first `docker run`.

## Core Concepts — Deployments (answers to the cold questions)
- `kubectl set image` → a **second ReplicaSet** with the new template; it scales up while the old scales to 0. Old pods are replaced (new names, new IPs). Old RS kept at 0 for `rollout undo`. = rolling update, the reason Deployments exist above ReplicaSets.
- `selector.matchLabels` ≠ template labels → apply **rejected**: "selector does not match template labels." Most common exam typo.
- Bare ReplicaSet instead of Deployment: almost never; Deployment = RS + rollout history + rolling updates.
- Never delete pods owned by a Deployment by hand — the RS recreates them. Edit the file and apply; or `kubectl delete deployment <name>` for everything.

## Local cluster
Docker Desktop → Settings → Kubernetes → Enable. Node name `desktop-control-plane` (kind-based; the node is a container in the VM, NOT my Mac — matters below).
```bash
kubectl config get-contexts              # had a stopped minikube — that was Tuesday's 127.0.0.1:57754 error
kubectl config use-context docker-desktop
kubectl get nodes                        # one node, Ready
minikube delete                          # reclaim disk (later)
```

## The Deployment (k8s/labs/deployment.yaml) — what was wrong and why
1. `apiversion` → `apiVersion`, `Metadata` → `metadata`. Keys are case-sensitive; API server rejects.
2. `image: cloud-sentinel:latest` with no pull policy → `:latest` defaults to `Always` → tries Docker Hub → `ImagePullBackOff`. Fix: `imagePullPolicy: IfNotPresent` (image is already in the same VM the cluster uses).
3. `hostPath` for `~/.aws` → `FailedMount: /Users/.../.aws is not a directory`. The kubelet looks on the **node**, and on this cluster the node is a container; my Mac's home isn't there. hostPath for credentials is a local-cluster hack anyway.
4. Fix: a **Secret**, holding only the `cloud-sentinel-ro` keys — root creds never leave the laptop. Delivered as env vars (`envFrom`), not a file; boto3's default chain reads them first.
5. `/findings` → 500, logs → `NoRegionError`. On Docker the profile's config file supplied the region; the Secret carries only identity. Fix: `AWS_DEFAULT_REGION` as a plain env var in the manifest — config, not secret.
6. `/data` → `emptyDir` for now. Three replicas = three separate scratch dirs, so `/findings/last` is per-pod. Real fix = PersistentVolumeClaim (Storage section).

Final shape:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-deployment
  labels: {app: my-app}
spec:
  replicas: 3
  selector:
    matchLabels: {app: my-app}
  template:
    metadata:
      labels: {app: my-app}
    spec:
      containers:
        - name: my-container
          image: cloud-sentinel:latest
          imagePullPolicy: IfNotPresent
          ports: [{containerPort: 8080}]
          env:
            - name: AWS_DEFAULT_REGION
              value: us-east-1
          envFrom:
            - secretRef: {name: aws-creds}
          volumeMounts:
            - name: sentinel-data
              mountPath: /data
      volumes:
        - name: sentinel-data
          emptyDir: {}   # per-pod scratch; PVC later
```

## apply vs replace — the subtle one
After editing hostPath → emptyDir and running `apply`, the `last-applied-configuration` annotation showed the new spec but the live `spec.template.spec.volumes` still had `hostPath`. `apply` does a three-way merge and can leave a replaced list element behind. Fix: `kubectl replace -f` (whole object, no merge) or delete + apply.
**Rule: the file is intent; the cluster is truth. After apply, `kubectl get <kind> <name> -o yaml` to confirm.**

## Debug chain used today (pod-status → component)
- `ContainerCreating` for minutes → `kubectl describe pod <name>` → Events → `FailedMount` from **kubelet** → volume problem, not image, not app.
- Rollout wedged (old 3 pods + 1 new stuck) → Deployment won't take old pods down until a new one is Ready. Fix the new pod's problem; rollout continues.
- `Running` + HTTP 500 → `kubectl logs` → Python traceback → app config problem.
- `kubectl describe <name>` without a kind → "server doesn't have a resource type" — kind comes first: `describe pod <name>`.

## Commands run today
```bash
# cluster
kubectl config get-contexts
kubectl config use-context docker-desktop
kubectl get nodes

# secret: only the read-only profile, via env file, then delete the file
aws configure export-credentials --profile cloud-sentinel-ro --format env-no-export > /tmp/ro.env
kubectl create secret generic aws-creds --from-env-file=/tmp/ro.env
rm /tmp/ro.env
kubectl get secret aws-creds -o jsonpath='{.data}' | head -c 200   # base64, not encrypted

# deploy
kubectl apply -f deployment.yaml
kubectl get pods
kubectl get pods -w                      # streams until Ctrl-C; not a hang
kubectl describe pod <pod> | tail -20    # Events at the bottom
kubectl get deployment my-deployment -o yaml | grep -A3 volumes   # cluster truth vs file
kubectl replace -f deployment.yaml       # when apply's merge leaves old list items
kubectl get all                          # 1 deploy, 3 RS (two at 0), 3 pods
kubectl logs deployment/my-deployment --tail=30

# reach it
kubectl port-forward deployment/my-deployment 8080:8080
curl localhost:8080/health               # {"ok": true}
curl localhost:8080/findings             # real findings via the Secret's creds

# cleanup when needed
kubectl delete deployment my-deployment
```

## Lines for the README
- Credentials: Docker = mounted profile file; Kubernetes local = Secret with only the least-privilege keys as env; EKS = Pod Identity, no secret at all.
- Region and identity were bundled in `~/.aws`; Kubernetes forced them apart — identity in a Secret, region in the manifest.
- hostPath is never the answer for credentials.

## Next
Services (lecture + lab) — replaces port-forward with a stable name/IP. Then Storage → PVC for `/data`.
