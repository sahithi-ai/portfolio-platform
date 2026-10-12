# 2026-10-11 — Services (Core Concepts closed), DNS inside the cluster

Streak restarted at 1 (no commit Oct 9–10). Build 9:20–12:20. Commit: `<hash>`.
Build weak-list: empty.

## What shipped
cloud-sentinel behind a Service: three pods, one name, one stable IP. Verified the Service from inside the cluster, the NodePort from the node, and cluster DNS by name. Old `my-deployment` replaced by `cloud-sentinel-deployment` with labels `app: cloud-sentinel-app` everywhere.

## Retrieval (cold)
- Deployment vs ReplicaSet: Deployment = RS + rollout history + rolling update. A bare RS can only "keep N running." Always Deployment.
- Service exists because pod IPs change on every restart/rollout. The Service is the stable name + virtual IP; a selector picks the pods behind it.

## Services — the model
- `selector` on the Service must match the **pod** labels (the template's labels, not the Deployment's). Mine said `app: cloud-sentinel` while pods carried `app: my-app` → Service with zero endpoints, no error anywhere. **A Service with no matching pods is silent; check `kubectl get endpoints <svc>` first.**
- Three types, stacked: ClusterIP (inside only) ⊂ NodePort (also a port 30000–32767 on every node) ⊂ LoadBalancer (also a cloud LB; on EKS an NLB/ALB via the AWS Load Balancer Controller).
- `port` = the Service's port (what callers use). `targetPort` = the container's port. Mine: 80 → 8080.
- The ClusterIP (`10.96.155.166`) is a **virtual IP** — it exists only as iptables/IPVS rules kube-proxy writes on each node, rewriting Service IP → a real pod IP. No interface has it. That's why nothing outside the cluster can route to it.

## The three-step test (where does the connection die?)
`curl localhost:30239` from the Mac failed. Don't edit YAML on a connection refused — locate the failure, inside → out.

| step | command | result |
|---|---|---|
| Service → pod (ClusterIP, by DNS) | `kubectl run curl --rm -it --image=curlimages/curl --restart=Never -- curl -s http://cloud-sentinel-service/health` | `{"ok":"True"}` ✓ |
| NodePort on the node | `docker exec desktop-control-plane curl -s http://localhost:30239/health` | `{"ok":"True"}` ✓ |
| Mac → node port | `curl localhost:30239/health` | refused ✗ |

Reading: Service and NodePort are correct. Docker Desktop's kind-style cluster doesn't publish node ports to macOS — the node is a container in the VM. Same wall as `172.17.0.2` on day one. **Not a Kubernetes bug; not a reason to go to EKS.** On EKS, port 30239 is open on each EC2 node's IP with zero YAML change.
Local door: `kubectl port-forward svc/cloud-sentinel-service 8080:80` — to the **Service**, so requests spread across pods, instead of pinning one pod.

## Cluster DNS — seen, not read
```
Server:    10.96.0.10          kube-dns.kube-system.svc.cluster.local   ← CoreDNS, itself behind a Service
Name:      cloud-sentinel-service
Address 1: 10.96.155.166       cloud-sentinel-service.default.svc.cluster.local
```
- Full name = `<service>.<namespace>.svc.cluster.local`. Short name works inside the same namespace because the kubelet writes `search default.svc.cluster.local ...` into every pod's `/etc/resolv.conf`. From another namespace: `cloud-sentinel-service.default`.
- Only pods ask CoreDNS. My Mac asks my router → the name doesn't exist in the browser, by design. = Compose's per-network DNS, one layer up.
- `"ok":"True"` is a string in my JSON. Should be the bool `True` → `true`. Fix on the next app.py touch.

## Debugging a one-off pod (new habit)
- `--rm -it` on `kubectl run` deleted the failed pod before I could see why → evidence gone. Rule: **no `--rm` when something might fail**; run, `kubectl logs <pod>`, then `kubectl delete pod <pod>`. Same loop I'll use for CronJob runs on EKS.
- `busybox:latest` nslookup misbehaves against CoreDNS; pin `busybox:1.28` (CKA-standard).
- `#` comment lines pasted alone into zsh → `command not found: #`. Harmless.

## Commands run today
```bash
kubectl apply -f deployment.yaml                   # renamed + relabeled Deployment
kubectl delete deployment my-deployment            # old one, old labels
kubectl apply -f service.yaml
kubectl get endpoints cloud-sentinel-service       # 3 pod IPs :8080 → selector matches (endpointslices is the newer command)
kubectl get svc cloud-sentinel-service             # CLUSTER-IP 10.96.155.166, PORT(S) 80:30239/TCP

# one-off pods
kubectl run curl --rm -it --image=curlimages/curl --restart=Never -- curl -s http://cloud-sentinel-service/health
kubectl run dns --image=busybox:1.28 --restart=Never -- nslookup cloud-sentinel-service
kubectl logs dns
kubectl delete pod dns

# from my own pod (slim has no curl → python)
kubectl exec deploy/cloud-sentinel-deployment -- python -c "import urllib.request; print(urllib.request.urlopen('http://cloud-sentinel-service/health').read())"

# from the node container
docker exec desktop-control-plane curl -s http://localhost:30239/health

# local door
kubectl port-forward svc/cloud-sentinel-service 8080:80 &
curl localhost:8080/health
kill %1

git add k8s/labs/service.yaml k8s/labs/deployment.yaml
git commit -m "feat(k8s): NodePort Service for cloud-sentinel, 3 replicas behind one name"
git push
```

## Files (final)
`k8s/labs/service.yaml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: cloud-sentinel-service
  labels: {app: cloud-sentinel-app}
spec:
  selector: {app: cloud-sentinel-app}     # must equal the POD labels
  ports:
    - protocol: TCP
      port: 80          # Service port
      targetPort: 8080  # container port
  type: NodePort
```

## Lines for the README — "Runs on Kubernetes"
- Three replicas behind a NodePort Service; verified from inside the cluster and from the node. Docker Desktop doesn't publish node ports to macOS; local access is `port-forward svc/`. On EKS the same manifest is reachable on node IPs; a LoadBalancer type would add an NLB.
- A Service with a wrong selector fails silently — `get endpoints` is the first check.

## Interview line
"A Service is a stable DNS name and virtual IP in front of a label-selected, changing set of pod IPs; kube-proxy programs each node to rewrite the virtual IP to a real pod IP."

## Next (same session)
Storage: PVC for `/data` so `/findings/last` survives pod deletion. Then `docker build --platform linux/amd64`.
