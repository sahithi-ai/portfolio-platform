# portfolio-platform

Platform engineering portfolio: Kubernetes on AWS, provisioned and managed with Terraform.

This repo collects my hands-on platform engineering projects. Each one is built end to end: infrastructure, deployment and operations.

## Topics

### Platform Engineering
**What it is:** Platform engineering means designing and running an internal developer platform: a set of shared tools, infrastructure and automated workflows. Development teams use it to build, deploy and run software on their own, without filing tickets for infrastructure.

**Why it matters:** It turns repeated infrastructure work into reusable, self-service building blocks, sometimes called "golden paths." Teams ship faster and more consistently, and security and reliability are built in by default.

### Kubernetes
**What it is:** Kubernetes (K8s) is an open-source container orchestration system. It automates deploying, scaling and managing containerized applications across a cluster of machines.

**Why it matters:** Kubernetes is the standard runtime layer for modern platforms. It handles scheduling, self-healing, rolling updates, service discovery and autoscaling. Workloads are described in declarative manifests, so they can be versioned and reviewed like code.

### Terraform
**What it is:** Terraform is an Infrastructure as Code (IaC) tool from HashiCorp. You define cloud and on-prem resources in declarative configuration files (HCL), then plan and apply changes to reach that desired state.

**Why it matters:** Infrastructure becomes versioned, reviewable and repeatable. You can recreate an environment from code, catch changes before they happen with `terraform plan`, and package common patterns as reusable modules.

### AWS
**What it is:** Amazon Web Services (AWS) is a cloud computing platform. It offers on-demand compute, storage, networking, databases and managed services such as EC2, S3, VPC, IAM and EKS (managed Kubernetes).

**Why it matters:** AWS provides the underlying infrastructure the platform runs on. Using its managed services means less low-level work, and the platform can scale with demand.

## How they fit together

```
Terraform  ──provisions──▶  AWS (VPC, IAM, EKS, ...)
                                 │
                                 ▼
                     Kubernetes (EKS cluster)
                                 │
                                 ▼
          Platform Engineering: self-service tooling,
          CI/CD, observability, and golden paths on top
```
