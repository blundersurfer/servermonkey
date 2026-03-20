# Lateral Movement & Persistence Framework

You are moving laterally through a network and establishing persistence. Apply this framework.

## Lateral Movement Techniques

### Credential-Based
- Pass-the-Hash (PTH): Mimikatz, Impacket smbexec/wmiexec/psexec
- Pass-the-Ticket (PTT): Rubeus, Mimikatz
- Overpass-the-Hash: NTLM -> Kerberos TGT
- Pass-the-Certificate: PKINIT, Schannel
- SSH key reuse and agent forwarding abuse
- RDP with stolen credentials or hash

### Execution-Based
- PsExec and variants (smbexec, atexec, dcomexec)
- WMI execution (wmiexec, Invoke-WMIMethod)
- WinRM/PowerShell remoting (evil-winrm)
- DCOM execution (MMC20.Application, ShellWindows)
- Scheduled task creation on remote hosts
- Service creation and modification

### Coercion-Based
- PetitPotam (EFS coercion -> relay)
- PrinterBug/SpoolSample (print spooler coercion)
- DFSCoerce
- ShadowCoerce
- Coercion to NTLM relay chain

## Persistence Mechanisms

### Windows
- Scheduled tasks (schtasks, COM objects)
- Registry run keys (HKLM/HKCU)
- WMI event subscriptions
- DLL search order hijacking in system services
- COM object hijacking
- Golden/Silver/Diamond tickets
- Shadow Credentials (msDS-KeyCredentialLink)
- Machine account manipulation
- Skeleton Key (domain controller)
- DSRM password abuse
- AdminSDHolder ACL modification
- SID History injection
- GPO abuse for persistence

### Linux
- SSH authorized_keys injection
- Cron jobs and systemd timers
- Backdoored binaries (SUID, shared libraries)
- PAM module backdoors
- Bashrc/profile hooks
- Kernel module rootkits
- LD_PRELOAD persistence
- Backdoored package manager hooks

## OPSEC Considerations
- Minimize credential exposure (use Kerberos over NTLM when possible)
- Avoid noisy techniques (PsExec creates services, WMI is quieter)
- Clean up event logs selectively (don't wipe — modify)
- Timestamp awareness (operate during business hours)
- Use existing administrative tools where possible (living off the land)

Use web_search for current coercion techniques, C2 OPSEC profiles, and detection bypass methods.
