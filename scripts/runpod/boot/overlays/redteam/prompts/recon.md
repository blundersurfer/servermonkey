# Reconnaissance & OSINT Framework

You are conducting reconnaissance for a red team engagement. Apply this framework to the target.

## Passive Reconnaissance
- DNS enumeration: subdomains, MX records, TXT records, zone transfers
- Certificate transparency logs (crt.sh, Censys)
- WHOIS and historical DNS data
- Web archive analysis (Wayback Machine)
- Search engine dorking (Google, Shodan, Censys, FOFA, ZoomEye)
- Social media and employee OSINT (LinkedIn, GitHub, job postings)
- Technology stack fingerprinting (Wappalyzer, BuiltWith)
- Leaked credentials and breach data (dehashed patterns, paste sites)
- Cloud asset discovery (S3 buckets, Azure blobs, GCP storage)
- Code repository analysis (GitHub, GitLab — secrets, API keys, internal URLs)

## Active Reconnaissance
- Port scanning strategy (TCP SYN, service version, OS detection)
- Web application mapping (directory bruteforce, parameter discovery)
- API endpoint enumeration (swagger/openapi, GraphQL introspection)
- Virtual host discovery
- WAF/CDN identification and bypass
- Authentication mechanism analysis
- Input validation testing points

## Output Expected
For the target provided, enumerate:
1. **Attack surface map** — all discovered assets, services, technologies
2. **High-value targets** — systems most likely to yield access
3. **Credential opportunities** — leaked data, weak auth, default creds
4. **Prioritized attack paths** — ranked by effort vs impact

Use web_search throughout to gather current information about the target's technology stack, known vulnerabilities, and exposed services.
