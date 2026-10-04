# cloud-sentinel

A containerized AWS security-posture scanner. v0 finds security groups with inbound rules open to the entire internet (`0.0.0.0/0` or `::/0`) across every enabled region in an account and serves the findings over HTTP.

Built as the first workload of a platform-engineering portfolio: the same image will run as a Kubernetes CronJob on EKS (provisioned with Terraform, deployed with Argo CD), expose Prometheus metrics, and later be exposed as an MCP tool for an AI agent. The program's shape never changes; the platform around it does.

## Status

| | |
|---|---|
| Version | v0 — Oct 4, 2026 |
| Check | Open security groups (inbound from the internet) |
| Regions | All regions enabled on the account |
| Interface | `GET /findings` → JSON |
| Runs on | Docker, locally |
| AWS identity | Dedicated read-only IAM user, three actions |
| Next | Non-root container user, `gunicorn`, `HEALTHCHECK`, `.dockerignore`, Compose, named volume for findings, `/metrics` |

## What it found

In my own account, on the first run: several `launch-wizard-*` security groups with SSH (tcp/22) open to `0.0.0.0/0` in us-east-1 — each one left behind by an EC2 console launch and never cleaned up. That is the exact class of exposure this tool exists to catch: not the region you work in, the one you forgot.

<!-- screenshot of /findings goes here -->

## How it works

```
docker run ──▶ app.py (Flask, port 8080)
                 │
                 ├─ GET /findings
                 │     └─ run_scan()
                 │          ├─ sts.get_caller_identity()      confirm which account we're in
                 │          ├─ ec2.describe_regions()          enabled regions only
                 │          └─ for each region:
                 │               ec2.describe_security_groups (paginated)
                 │               └─ for each inbound rule:
                 │                    source is 0.0.0.0/0 or ::/0 ?  → finding
                 │                    port range covers 22/3389/3306/5432/6379/27017 ? → HIGH, else MEDIUM
                 └─ credentials: boto3 default chain (mounted ~/.aws + AWS_PROFILE, or env vars)
```

Each finding records: `region`, `group_id`, `group_name`, `vpc_id`, `ports`, `cidrs`, `severity`, `services`.

## Run it

```bash
docker build -t cloud-sentinel .

docker run -p 8080:8080 \
  -v ~/.aws:/root/.aws:ro \
  -e AWS_PROFILE=<your-profile> \
  cloud-sentinel

curl http://localhost:8080/findings
```

The profile needs only `ec2:DescribeRegions`, `ec2:DescribeSecurityGroups` and `sts:GetCallerIdentity`. The scanner runs under a dedicated read-only IAM user (`cloud-sentinel-ro`) with an inline policy allowing exactly those three actions — not an admin profile. Read-only; the scanner changes nothing.

On macOS, `http://localhost:8080/findings` is the only way in. Flask also prints the container's bridge IP (`172.17.0.x`), which is reachable on a Linux host but not from a Mac — Docker Desktop runs the engine inside a Linux VM, and the bridge network lives there. See *Engineering notes*.

## Design decisions

**Credentials are never in the image.** Nothing in the Dockerfile references AWS keys. At run time the host's `~/.aws` is mounted read-only and the profile name is passed as an environment variable; boto3's default credential chain finds it. Anything baked into an image lives in every layer, in every registry it is ever pushed to. On EKS this mount goes away entirely and the pod receives a role through Pod Identity / IRSA.

**Least privilege on the AWS side.** The container runs as `cloud-sentinel-ro`, an IAM user whose only permissions are the three read-only actions the scan needs. Verified by running `aws ec2 describe-instances` under the same profile and getting `AccessDenied`. A container only ever holds the permissions of the identity it was given — if this one were compromised, the blast radius is "can list security groups," not "owns the account." Two separate "users" matter here: the Linux user the process runs as inside the container (`USER` in the Dockerfile — v0.1), and the AWS identity the process calls the API with (this one).

**Every API call has a timeout.** `botocore.config.Config(connect_timeout=5, read_timeout=15, retries={'max_attempts': 2})` on every client. Without it, boto3's defaults (60-second connect, up to four attempts) turn an unreachable endpoint into minutes of silence. A region that cannot be reached now costs about ten seconds and is logged, and the scan continues.

**Enabled regions only.** `describe_regions()` without `AllRegions=True` returns the regions the account can actually use. Scanning opt-in regions the account hasn't enabled produces errors, not findings.

**Expected failures are caught; unexpected ones crash.** The per-region `except` catches `ClientError`, `EndpointConnectionError` and `ConnectTimeoutError` — the things a region can legitimately do to you. A bare `except Exception` would also swallow a typo in the scan logic and report it as "region failed."

**Paginated from the start.** `describe_security_groups` returns up to 1,000 groups per page. A paginator means the scan is correct in an account with 50 groups and in one with 5,000.

**Dependencies are installed before code is copied.** The `pip install` layer is cached until `requirements.txt` changes; editing `app.py` rebuilds only the layers after it.

**`python:3.14-slim`, not `python:3.14`.** The full image is roughly a gigabyte of Debian and build tools the scanner never uses; slim is a fraction of that with the same Python.

## Engineering notes

*What happened the first time it ran, and what it taught.*

- The first multi-region run hung for minutes on one region. `curl -m 5 https://ec2.me-south-1.amazonaws.com` timed out in five seconds — the endpoint was unreachable from my network, nothing in the code could have fixed it, only tolerated it. That became the timeout rule above. The region was in the list because of an `AllRegions=True` flag I had added while experimenting; the account API confirmed the region was disabled. Lesson: when two AWS APIs disagree about your own account, read the flags you passed before suspecting the service.
- `docker run <image>` needs an image name; `.` belongs to `docker build .`. The container can't see the shell's exported `AWS_PROFILE` — the environment boundary is the whole point — so it is passed with `-e`.
- Without a `USER` instruction the process runs as root and boto3 looks for credentials in `/root/.aws`. Once the image runs as a non-root user, the mount path moves to that user's home. Mounting to the wrong one fails with "Unable to locate credentials," not with a path error.
- Flask started and printed three addresses. `127.0.0.1:8080` worked; `172.17.0.2:8080` loaded forever. The second is the container's IP on Docker's default bridge network. On a Linux host that address is routable from the host; on macOS the engine runs in a hidden Linux VM and the bridge lives inside it, so the Mac has no route to `172.17.x.x`. The published port (`-p 8080:8080`) is the only door in on a Mac. The `192.168.65.1` in the request log is the Mac itself as seen from inside the VM. Same idea one layer up: on Kubernetes, pods have their own IPs and a Service is the door.
- Flask's built-in server warns that it is a development server. It is. v0.1 runs the app under `gunicorn`.

## Why this runs on Kubernetes and not Lambda

For a scan that runs once an hour, Lambda plus EventBridge is cheaper and simpler, and it is what I would reach for at work. It runs on EKS here because this portfolio exists to prove I can build and operate the platform underneath workloads like this one — the cluster, the GitOps pipeline, the observability — and a CronJob is the honest, small workload to prove it with.

## Roadmap

- **v0.1** — non-root container user, `gunicorn` instead of the Flask dev server, `HEALTHCHECK`, `.dockerignore`, Compose file, findings persisted to a named volume
- **v0.2** — `/metrics` in Prometheus format (`sentinel_findings_total{check,severity,region}`)
- **v0.3** — second check: S3 buckets with public access; severity `CRITICAL` for "all traffic" rules
- **Platform (Nov)** — CronJob on EKS via Argo CD, Terraform-provisioned, Pod Identity instead of mounted credentials, Grafana dashboard
- **Agent (Jan)** — exposed as an MCP tool so an agent can answer "what is exposed in my account right now?"

## Limitations (v0)

- Security groups only; no NACLs, no S3, no IAM.
- Findings are not persisted; every `GET /findings` rescans.
- Single-threaded; ~17 regions scanned sequentially.
- No authentication on the endpoint — local use only.
