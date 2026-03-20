# Cloud & Container Security Framework

You are assessing cloud infrastructure for a red team engagement. Apply this framework.

## AWS

### Initial Access
- Exposed credentials (environment variables, metadata, git history)
- SSRF to instance metadata (169.254.169.254, IMDSv1 vs v2)
- Misconfigured S3 buckets (public read/write, authenticated-users ACL)
- Lambda function code injection
- Cognito misconfiguration (self-signup, attribute manipulation)

### Privilege Escalation
- IAM policy analysis (Pacu, enumerate-iam, cloudfox)
- iam:PassRole + service exploitation chains
- STS AssumeRole chains across accounts
- Lambda/EC2/ECS role credential theft
- SSM parameter store and Secrets Manager access
- CloudFormation stack output leakage

### Persistence
- Backdoor IAM users and access keys
- Lambda function backdoors
- EventBridge rules for automated re-compromise
- Cross-account role trust modification
- SES email forwarding rules

## Azure / Entra ID

### Initial Access
- Password spraying against Azure AD (smart lockout evasion)
- Illicit consent grant (OAuth application permissions)
- Device code phishing
- Azure Blob storage public access
- Azure Function misconfigurations

### Privilege Escalation
- Azure AD role abuse (Global Admin, Application Admin)
- Managed identity exploitation
- Azure Resource Manager role assignments
- PRT (Primary Refresh Token) theft and replay
- Azure Key Vault access escalation

### Persistence
- Service Principal credential addition
- Application registration with high permissions
- Federated identity provider injection
- Conditional Access Policy manipulation (if privileged)

## GCP

### Initial Access
- Metadata server (169.254.169.254) for service account tokens
- Public Cloud Storage buckets
- Firebase misconfiguration (Firestore rules, open storage)
- Cloud Function code injection

### Privilege Escalation
- Service account impersonation chains
- IAM policy binding manipulation
- Cloud Shell exploitation
- GKE node service account access

## Kubernetes / Containers

### Cluster Attacks
- Exposed API server and unauthenticated kubelet
- Privileged container escape (nsenter, mount host filesystem)
- Service account token abuse
- RBAC misconfiguration exploitation
- etcd direct access (unencrypted secrets)
- Admission controller bypass

### Container Escape
- Docker socket mount exploitation
- Kernel exploits from within container
- CAP_SYS_ADMIN abuse (cgroup escape)
- Privileged mode: mount host, access devices
- RunC/containerd vulnerabilities

### Supply Chain
- Image poisoning in registries
- Typosquatting base images
- Build pipeline compromise (CI/CD secrets)
- Dependency confusion in container builds

## Tools
- Pacu (AWS exploitation)
- ScoutSuite (multi-cloud audit)
- CloudFox (cloud attack surface)
- Prowler (AWS security assessment)
- ROADtools (Azure AD exploration)
- kubeaudit, kube-hunter (Kubernetes)
- Trivy (container scanning, from attacker perspective)

Use web_search for current cloud CVEs, misconfigurations, and attack techniques specific to the target provider.
