# 2026-10-06 — Docker under the hood, volumes, networking, Compose (review doc)

Docker course finished. This is the concept map, written to re-read before CKA and again before the EKS workshop.

## Retrieval (morning)
- Paginator: one page per call; keep calling until `NextToken` is empty. Without it you get page one and silently miss the rest.
- `-v name:path` → named volume. `-v /host/path:path[:ro]` → bind mount. Slash or no slash is how Docker tells them apart. Off the weak-list.

## Three layers on a Mac (not two)
1. **My Mac** — macOS, terminal, browser, `~/.aws`, the `docker` *client*. The client only sends requests.
2. **Docker Desktop's hidden Linux VM** — containers need a Linux kernel; macOS doesn't have one. The **daemon** (`dockerd`) lives here and does all the work: builds, runs, networks, volumes. Client ↔ daemon over `docker.sock` (Sunday's "cannot connect to the daemon" = VM not up).
3. **The container** — a normal Linux process (gunicorn + `app.py`) inside the VM with walls around it: namespaces (isolation), cgroups (limits). Not a VM.

On a Linux server there are only two layers; the host is the Linux machine. Some things work there that don't on a Mac — same on EKS nodes.

## Where things live
- **Image**: built by the daemon from my folder (minus `.dockerignore`), stored inside the VM at `/var/lib/docker`. Never a file on my Mac. `docker images` = client asking the daemon.
- **Container filesystem**: image's read-only layers + one thin writable layer on top. Writes go to the writable layer; `docker rm` deletes it. (= instance store)
- **Named volume** `sentinel-data`: daemon-owned directory inside the VM (`/var/lib/docker/volumes/sentinel-data/_data`). Outlives containers. Can't `ls` it from the Mac. (= EBS)
- **Bind mount** `~/.aws`: a real Mac folder shared into the VM via file sharing, mounted into the container at `/home/app/.aws`. Only way the container sees my Mac. Slower on macOS because it crosses the VM boundary. (= EFS)

Proven last night: no volume → `/findings/last` gone after `rm`; named volume → survives.

## Networking — the four addresses
- **`127.0.0.1` inside the container** — the container's own loopback. Only the container can reach it. Every machine and every container has its own `127.0.0.1`; same number, different places, invisible to each other.
- **`172.17.0.2`** — container IP on Docker's `bridge` network, a virtual switch *inside the VM*. Linux host could reach it; my Mac can't (not on that switch). That's why it hung in the browser.
- **`192.168.65.1`** — my Mac as seen from inside the VM (the gateway). Requests from my browser show up as this in gunicorn's log.
- **`localhost:8080` on my Mac** — exists only because of `-p 8080:8080`. Docker Desktop binds the Mac's port and forwards Mac → VM → container's 8080. The single door between Mac and container.

**How `127.0.0.1:8080` in my browser worked:** it hit *my Mac's* loopback, not the container's. Browser → Mac :8080 → Docker Desktop forward → VM → container `eth0` (172.x) :8080 → gunicorn. Flask's "Running on 127.0.0.1" line was Flask listing its own interfaces from inside.
**Why `host="0.0.0.0"` matters:** "listen on every interface" including `eth0`, where forwarded traffic arrives. Listening only on the container's `127.0.0.1` → port-forward finds nothing → connection fails.

**Networks:**
- `bridge` (default) — containers reach each other by IP only, no DNS.
- user-defined bridge (`cloud-sentinel_default`, created by Compose) — adds DNS; containers resolve each other by **service name**. `curl http://sentinel:8080/health` from a second container on the same network works; without `--network` it fails with "could not resolve host."
- `host` — container shares the VM's network, no isolation, no `-p` needed.
- `none` — no network.

Lab commands:
```bash
docker network ls
docker network inspect cloud-sentinel_default
docker run --rm --network cloud-sentinel_default curlimages/curl http://sentinel:8080/health   # works
docker run --rm curlimages/curl http://sentinel:8080/health                                     # could not resolve host
```
`--rm` = delete on exit. `curlimages/curl` = image that is just curl. Everything after the image name = the command. `8080` here is the container port — this call never leaves Docker's network.

## Credentials, end to end
`-e AWS_PROFILE` sets an env var on the container's process (the container can't see my shell's exports — the boundary is the point). boto3 reads the profile name, opens `/home/app/.aws/credentials` (my Mac's file via the bind mount), then calls AWS: container → VM network → Mac network → internet. The me-south-1 timeout was that last hop failing.

## Engine (read-only)
Three separate programs: **client** (`docker`), **daemon** (`dockerd`, in the VM on a Mac), **registry** (Docker Hub / ECR). `docker info` → storage driver `overlay2` (the layered filesystem), counts, server OS. `docker system df` → disk by images / containers / volumes / cache.

## Compose
`compose.yaml` = my eight-flag `docker run` line as a file.
```yaml
services:
  sentinel:                       # service name = DNS name on the compose network
    build: .                      # docker build .
    ports: ["8080:8080"]          # -p
    volumes:
      - ~/.aws:/home/app/.aws:ro  # bind mount
      - sentinel-data:/data       # named volume
    environment:
      AWS_PROFILE: cloud-sentinel-ro   # -e
    restart: unless-stopped       # --restart
volumes:
  sentinel-data:                  # declares the named volume
```
Healthcheck comes from the Dockerfile. Container name = `cloud-sentinel-sentinel-1` unless `container_name:` is set.
`docker compose up -d` · `ps` · `logs -f` · `down` (keeps volume; `down -v` deletes it — don't).

## The picture
```
Mac (macOS)
│  docker CLI ──socket──┐        ~/.aws (real folder)
│  browser → localhost:8080      │  (file sharing)
└─ Docker Desktop VM (Linux) ────┼──────────────────────
   │  dockerd ◄──────────┘       │
   │  /var/lib/docker/ images, volumes/sentinel-data ──┐
   │  networks: bridge, cloud-sentinel_default (DNS)   │
   └─ container: gunicorn ← app.py                     │
        /home/app/.aws ◄─ bind mount (ro)              │
        /data ◄─ named volume ─────────────────────────┘
        eth0 172.x on cloud-sentinel_default
        :8080 ◄── forwarded from Mac :8080
```

## Same picture, Kubernetes labels (November)
| Docker | Kubernetes |
|---|---|
| the VM | node |
| container | inside a pod |
| named volume | PersistentVolumeClaim |
| compose network + DNS | Service |
| `-p` mapping | Ingress / LoadBalancer |
| bind-mounted credentials | Pod Identity / IRSA |
| `--restart` + healthcheck | liveness probe + kubelet restart |
| `compose.yaml` | Deployment manifest |

## Weak-list (Build)
1. flags-before-image (bitten twice)
2. paginator — mechanism, said cold
