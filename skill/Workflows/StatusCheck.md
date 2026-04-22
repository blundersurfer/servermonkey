# Status Check Workflow

## Purpose
Quick cluster health check — node status, running guests, resource usage, and recent tasks.

## Steps

1. **List nodes**: Call `list_nodes` to get all cluster nodes
2. **Check each node**: For each node, call `node_status` to get CPU, memory, uptime
3. **List guests**: Call `list_vms` and `list_containers` on each node
4. **Summarize**: Present a table with:
   - Node name, status, CPU usage %, memory usage %, uptime
   - Count of running/stopped VMs and CTs per node
5. **Recent tasks** (optional): Call `list_tasks` on each node, highlight any failed tasks

## Example Output Format

```
## Cluster Health

| Node | Status | CPU | Memory | Uptime | VMs | CTs |
|------|--------|-----|--------|--------|-----|-----|
| pve1 | online | 12% | 45%    | 30d    | 3/5 | 8/10 |

### Recent Failed Tasks
- None found ✓
```

## When to Use
- User asks "how's the cluster?" or "status check"
- Before provisioning, to identify which node has resources
- Troubleshooting — checking if a node is overloaded
