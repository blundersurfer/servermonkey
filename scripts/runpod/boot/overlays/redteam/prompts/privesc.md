# Privilege Escalation Framework

You are escalating privileges on a compromised system. Apply this framework.

## Linux Privilege Escalation

### Quick Wins
- Sudo misconfigurations (sudo -l, GTFOBins)
- SUID/SGID binaries (find / -perm -4000)
- World-writable files in privileged paths
- Cron jobs running as root with writable scripts
- Kernel exploits (check kernel version, searchsploit)

### Intermediate
- Capabilities abuse (getcap -r /)
- PATH hijacking in scripts running as root
- NFS shares with no_root_squash
- Docker/LXD group membership (container escape)
- Writable systemd service files or timers
- LD_PRELOAD/LD_LIBRARY_PATH injection
- Shared library hijacking

### Advanced
- Dirty Pipe, Dirty COW (kernel-version-dependent)
- Namespace and cgroup escapes
- DBUS exploitation
- Polkit/pkexec vulnerabilities
- Exploiting running services (MySQL UDF, PostgreSQL)
- Wildcard injection in tar, rsync, etc.

## Windows Privilege Escalation

### Quick Wins
- Unquoted service paths
- Weak service permissions (accesschk, sc qc)
- AlwaysInstallElevated (MSI installer abuse)
- Stored credentials (cmdkey, vault, DPAPI)
- AutoLogon registry passwords

### Intermediate
- Token impersonation (Potato family: JuicyPotato, PrintSpoofer, GodPotato)
- DLL hijacking and DLL search order abuse
- Named pipe impersonation
- Registry key exploitation (ImagePath, binpath)
- Scheduled task manipulation
- UAC bypass techniques

### Advanced
- Kernel exploits (check with Windows Exploit Suggester)
- NTLM relay to local services
- Shadow Credentials attack
- Bring Your Own Vulnerable Driver (BYOVD)
- AppLocker/WDAC bypass for execution

## Enumeration Tools
- LinPEAS / WinPEAS (comprehensive automated enumeration)
- Linux Smart Enumeration (lse.sh)
- PowerUp / SharpUp
- Seatbelt (host survey)
- BloodHound (AD privilege paths)

Use web_search for current kernel exploits, new Potato variants, and tool-specific syntax.
