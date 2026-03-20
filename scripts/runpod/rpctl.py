#!/usr/bin/env python3
"""
RunPod GPU pod management CLI.

Manages pod lifecycle for AI research infrastructure.
All access via SSH tunnels — no HTTP ports exposed.

Usage:
    rpctl.py launch quick                 # Spot RTX 4090
    rpctl.py launch research --on-demand  # On-demand for long sessions
    rpctl.py launch heavy --gpu-count 4   # 4× A100 SXM
    rpctl.py status                       # List running pods
    rpctl.py connect <pod-id>             # SSH tunnel (auto-detects template)
    rpctl.py terminate <pod-id>           # Graceful shutdown
    rpctl.py budget                       # View balance + spending

Environment variables:
    RUNPOD_API_KEY   - RunPod API key (required)
    RUNPOD_VOLUME_ID - Network volume ID (required for launch)

GUARDRAIL: This CLI cannot add funds or modify payment methods.
           Those operations require the RunPod web UI.
"""

import argparse
import os
import sys

try:
    import runpod
except ImportError:
    print("ERROR: runpod package not installed. Run: pip install runpod")
    sys.exit(1)


def _get_api_key() -> str:
    """Retrieve RunPod admin API key from libsecret keyring, falling back to env var.

    Stored as: service=runpod-admin, username=shuri
    """
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret

        schema = Secret.Schema.new(
            "org.freedesktop.Secret.Generic",
            Secret.SchemaFlags.NONE,
            {
                "service": Secret.SchemaAttributeType.STRING,
                "username": Secret.SchemaAttributeType.STRING,
            },
        )
        token = Secret.password_lookup_sync(
            schema,
            {"service": "runpod-admin", "username": "shuri"},
            None,
        )
        if token:
            return token
    except Exception:
        pass  # libsecret not available — fall back to env var

    # Fall back to environment variable
    key = os.environ.get("RUNPOD_API_KEY", "")
    if key:
        return key

    print("ERROR: RunPod API key not found.")
    print("  Expected in keyring: service=runpod-admin, username=shuri")
    print("  Or set env var:      export RUNPOD_API_KEY=<your-key>")
    sys.exit(1)


# Template profiles — GPU, image, and tunnel configuration
TEMPLATES = {
    "quick": {
        "image": "ollama/ollama:latest",
        "gpu": "NVIDIA GeForce RTX 4090",
        "disk": 20,
        "cloud_type": "COMMUNITY",
        "env": {
            "TEMPLATE": "quick",
            "OLLAMA_MODELS": "/runpod-volume/models/ollama",
        },
        "tunnels": [8080, 11434],
        "description": "Ollama + Open WebUI for interactive chat",
    },
    "research": {
        "image": "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04",
        "gpu": "NVIDIA L40S",
        "disk": 30,
        "cloud_type": "COMMUNITY",
        "env": {
            "TEMPLATE": "research",
            "MODEL_DIR": "/runpod-volume/models/vllm",
        },
        "tunnels": [8888, 8000],
        "description": "vLLM + Jupyter for research",
    },
    "heavy": {
        "image": "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04",
        "gpu": "NVIDIA A100-SXM4-80GB",
        "gpu_count": 2,
        "disk": 50,
        "cloud_type": "COMMUNITY",
        "env": {
            "TEMPLATE": "heavy",
            "MODEL_DIR": "/runpod-volume/models/vllm",
        },
        "tunnels": [8888, 8000],
        "description": "Multi-GPU vLLM + Jupyter",
    },
}


def _get_volume_id() -> str:
    """Get network volume ID from env var or API query."""
    vol_id = os.environ.get("RUNPOD_VOLUME_ID", "")
    if vol_id:
        return vol_id

    # Auto-detect from API
    try:
        from runpod.api.graphql import run_graphql_query
        result = run_graphql_query(
            'query { myself { networkVolumes { id name } } }'
        )
        volumes = result.get("data", {}).get("myself", {}).get("networkVolumes", [])
        if len(volumes) == 1:
            return volumes[0]["id"]
        elif len(volumes) > 1:
            print("Multiple network volumes found. Set RUNPOD_VOLUME_ID:")
            for v in volumes:
                print(f"  {v['id']}  {v['name']}")
            sys.exit(1)
    except Exception:
        pass

    print("ERROR: No network volume found. Create one in the RunPod console.")
    sys.exit(1)


def cmd_launch(args):
    """Launch a GPU pod from a template profile."""
    volume_id = _get_volume_id()

    t = TEMPLATES[args.template]
    env = dict(t["env"])
    cloud = "SECURE" if args.on_demand else t["cloud_type"]
    gpu_count = args.gpu_count or t.get("gpu_count", 1)

    if args.model:
        env["MODEL"] = args.model
    if args.overlay:
        env["OVERLAY"] = args.overlay

    print(f"Launching {args.template} pod...")
    print(f"  Image:    {t['image']}")
    print(f"  GPU:      {gpu_count}× {t['gpu']}")
    print(f"  Pricing:  {cloud}")
    print(f"  Volume:   {volume_id}")

    pod = runpod.create_pod(
        name=f"{args.template}-session",
        image_name=t["image"],
        gpu_type_id=t["gpu"],
        gpu_count=gpu_count,
        container_disk_in_gb=t["disk"],
        network_volume_id=volume_id,
        cloud_type=cloud,
        support_public_ip=True,
        start_ssh=True,
        ports="22/tcp",
        env=env,
        docker_args="bash /runpod-volume/shared/scripts/boot.sh",
    )

    pod_id = pod.get("id", "unknown")
    print(f"\nPod {pod_id} launching ({cloud})")
    print(f"Run 'rpctl.py status' to check when ready")
    print(f"Run 'rpctl.py connect {pod_id}' to SSH in with tunnels")


def cmd_status(args):
    """List all pods with status and GPU info."""
    pods = runpod.get_pods()
    if not pods:
        print("No pods running.")
        return

    print(f"{'ID':25s}  {'Name':20s}  {'Status':12s}  {'GPU':s}")
    print("-" * 70)
    for p in pods:
        pod_id = p.get("id", "?")
        name = p.get("name", "?")
        status = p.get("desiredStatus", "?")
        gpu_count = p.get("gpuCount", 1)
        gpu_type = p.get("machine", {}).get("gpuDisplayName", "?") if p.get("machine") else "?"
        print(f"{pod_id:25s}  {name:20s}  {status:12s}  {gpu_count}× {gpu_type}")


def cmd_connect(args):
    """SSH into a pod with auto-detected tunnel ports."""
    pod = runpod.get_pod(args.pod_id)
    if not pod:
        print(f"ERROR: Pod {args.pod_id} not found")
        sys.exit(1)

    runtime = pod.get("runtime")
    if not runtime:
        print(f"ERROR: Pod {args.pod_id} is not running yet. Check 'rpctl.py status'")
        sys.exit(1)

    ports = runtime.get("ports", [])
    ssh_port = next((p for p in ports if p.get("privatePort") == 22), None)

    if not ssh_port:
        print("ERROR: No SSH port found on this pod")
        sys.exit(1)

    ip = ssh_port["ip"]
    port = ssh_port["publicPort"]

    # Auto-detect template from pod name for tunnel setup
    pod_name = pod.get("name", "")
    template = pod_name.split("-")[0] if pod_name else ""
    tunnels = TEMPLATES.get(template, {}).get("tunnels", [8888, 8000])
    tunnel_args = " ".join(f"-L {p}:localhost:{p}" for p in tunnels)

    cmd = f"ssh -o StrictHostKeyChecking=accept-new {tunnel_args} root@{ip} -p {port}"
    print(f"Connecting to {pod_name or args.pod_id}...")
    print(f"Tunnels: {', '.join(f'localhost:{p}' for p in tunnels)}")
    print(f"Command: {cmd}")
    print()

    os.execvp("ssh", cmd.split())


def cmd_terminate(args):
    """Terminate a pod (stops billing)."""
    print(f"Terminating pod {args.pod_id}...")
    runpod.terminate_pod(args.pod_id)
    print(f"Pod {args.pod_id} terminated.")


def cmd_budget(args):
    """View account info and active pods. READ ONLY."""
    user = runpod.get_user()
    pods = runpod.get_pods()

    print("RunPod Account")
    print("-" * 40)
    print(f"  User ID:        {user.get('id', '?')}")
    print(f"  Network vols:   {len(user.get('networkVolumes', []))}")
    print(f"  Active pods:    {len(pods)}")

    if pods:
        print()
        print("Active pods:")
        for p in pods:
            name = p.get("name", "?")
            gpu_count = p.get("gpuCount", 1)
            cost = p.get("costPerHr", "?")
            print(f"  - {name}: {gpu_count}x GPU, ${cost}/hr")

    print()
    print("  For balance/billing: https://www.runpod.io/console/user/billing")
    print("  To add funds: use the RunPod web UI (not available via API)")

    # GUARDRAIL: No add_funds(), no modify_payment(), no update_billing().
    # Financial operations require human action through the RunPod web UI.


def main():
    parser = argparse.ArgumentParser(
        prog="rpctl.py",
        description="RunPod GPU pod management for AI research.",
        epilog="GUARDRAIL: This CLI cannot add funds. Use the RunPod web UI for billing.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # launch
    launch_p = sub.add_parser("launch", help="Launch a GPU pod from a template")
    launch_p.add_argument(
        "template",
        choices=TEMPLATES.keys(),
        help="Template profile to launch",
    )
    launch_p.add_argument(
        "--on-demand",
        action="store_true",
        help="Use on-demand pricing instead of spot",
    )
    launch_p.add_argument(
        "--model",
        help="Override default model path on the volume",
    )
    launch_p.add_argument(
        "--gpu-count",
        type=int,
        help="Override GPU count (useful for heavy template)",
    )
    launch_p.add_argument(
        "--overlay",
        help="Overlay to apply after base template (e.g., redteam)",
    )

    # status
    sub.add_parser("status", help="List running pods")

    # connect
    connect_p = sub.add_parser("connect", help="SSH into a pod with tunnels")
    connect_p.add_argument("pod_id", help="Pod ID to connect to")

    # terminate
    term_p = sub.add_parser("terminate", help="Terminate a pod")
    term_p.add_argument("pod_id", help="Pod ID to terminate")

    # budget
    sub.add_parser("budget", help="View account balance and spending (read-only)")

    args = parser.parse_args()

    # API key from libsecret keyring (preferred) or RUNPOD_API_KEY env var
    runpod.api_key = _get_api_key()

    commands = {
        "launch": cmd_launch,
        "status": cmd_status,
        "connect": cmd_connect,
        "terminate": cmd_terminate,
        "budget": cmd_budget,
    }
    commands[args.cmd](args)


if __name__ == "__main__":
    main()
