# Self-Hosted Control Panel Comparison

> **Architecture Decision Record** — Evaluating open-source control panels for managing hobby websites, backends, and middleware on free-tier cloud VMs.

## Use Case

Deploy and manage hobby websites, backend APIs, and middleware services on OCI free-tier VMs (ARM64 + x86) with:

- Git-based CI/CD deployment (push-to-deploy)
- Docker support for containerized workloads
- SSL certificate automation (Let's Encrypt)
- Low resource overhead (1 GB RAM on x86 micro instances)
- Long-term sustainability — the project should still exist in 2+ years

## Candidates

| Panel | License | Stars | Last Commit | Min RAM | Architecture |
|-------|---------|-------|-------------|---------|-------------|
| [Coolify](https://coolify.io) | Apache 2.0 | ~50.9K | Feb 2026 | 2 GB | x86, ARM64 |
| [CapRover](https://caprover.com) | Apache 2.0 | ~14.9K | Jan 2026 | 1 GB | x86, ARM64, ARMv7 |
| [HestiaCP](https://hestiacp.com) | GPL v3 | ~4.2K | Feb 2026 | 1 GB | x86, ARM64 |
| [CyberPanel](https://cyberpanel.net) | GPL v3 | ~1.9K | Feb 2026 | 1 GB | x86 only |
| [CloudPanel](https://cloudpanel.io) | MIT | ~1.8K | Sep 2025 | 1 GB | x86, ARM64 |
| [Virtualmin](https://virtualmin.com) | GPL / Pro | N/A¹ | Feb 2026 | 256 MB | x86, ARM64 |

¹ Virtualmin's core (Webmin) is on GitHub (~3.7K stars) but Virtualmin modules are distributed via their own repos.

---

## Feature Comparison

### Web Hosting & Application Stack

| Feature | Coolify | CapRover | HestiaCP | CyberPanel | CloudPanel | Virtualmin |
|---------|---------|----------|----------|------------|------------|------------|
| **Web server** | Traefik (auto) | Nginx (Docker) | Nginx/Apache | OpenLiteSpeed | Nginx | Apache/Nginx |
| **PHP support** | Via Docker | Via Docker | 5.6–8.4 native | 7.4–8.5 native | 7.1–8.4 native | 5.x–8.x native |
| **Node.js** | ✅ Native | ✅ Native | ❌ Manual | ✅ Via Docker | ✅ Native | ❌ Manual |
| **Python** | ✅ Native | ✅ Native | ❌ Manual | ✅ Via Docker | ✅ Native | ❌ Manual |
| **Go/Rust/etc** | ✅ Any Dockerfile | ✅ Any Dockerfile | ❌ | ❌ | ❌ | ❌ |
| **Multi-PHP versions** | Via Docker | Via Docker | ✅ Built-in | ✅ Built-in | ✅ Built-in | ✅ Built-in |
| **Database** | Any (Docker) | Any (Docker) | MariaDB/MySQL/PG | MariaDB | MySQL/MariaDB | MariaDB/MySQL/PG |
| **DNS server** | ❌ | ❌ | ✅ BIND | ✅ PowerDNS | ❌ | ✅ BIND |
| **Mail server** | ❌ | ❌ | ✅ Exim/Dovecot | ✅ SnappyMail | ❌ | ✅ Postfix/Dovecot |
| **FTP server** | ❌ | ❌ | ✅ vsftpd | ✅ Pure-FTPd | ✅ ProFTPd | ✅ ProFTPd |

**Sources**: [Coolify features](https://coolify.io/docs/), [CapRover docs](https://caprover.com/docs/get-started.html), [HestiaCP installer flags](https://docs.hestiacp.com/docs/introduction/getting-started.html), [CyberPanel features](https://github.com/usmannasir/cyberpanel), [CloudPanel stack](https://www.cloudpanel.io/docs/v2/technology-stack/), [Virtualmin OS support](https://www.virtualmin.com/docs/os-support)

### CI/CD & Deployment

| Feature | Coolify | CapRover | HestiaCP | CyberPanel | CloudPanel | Virtualmin |
|---------|---------|----------|----------|------------|------------|------------|
| **Git push-to-deploy** | ✅ Native | ✅ Via CLI/webhook | ❌ | ❌ | ❌ | ❌ |
| **GitHub integration** | ✅ GitHub App | ✅ GitHub Action | ❌ | ❌ | ❌ | ❌ |
| **GitLab integration** | ✅ Native | ✅ Via webhook | ❌ | ❌ | ❌ | ❌ |
| **Bitbucket/Gitea** | ✅ Native | ❌ | ❌ | ❌ | ❌ | ❌ |
| **PR preview deploys** | ✅ Native | ✅ Via workflow | ❌ | ❌ | ❌ | ❌ |
| **Webhook endpoint** | ✅ Built-in | ✅ Built-in | ❌ | ❌ | ❌ | ❌ |
| **REST API** | ✅ Full | ✅ App-level | ✅ Full (`v-*` CLI) | ✅ Limited | ❌ | ✅ Full (Webmin API) |
| **CLI tool** | ✅ [coolify-cli](https://github.com/coollabsio/coolify-cli) | ✅ `caprover` npm | ✅ `v-*` commands | ✅ `cyberpanel` CLI | ❌ | ✅ `virtualmin` CLI |
| **Docker support** | ✅ Core architecture | ✅ Core (Swarm) | ❌ | ✅ Container mgmt | ❌ | ❌ |
| **One-click services** | ✅ 280+ templates | ✅ Community apps | ❌ | ❌ | ❌ | ✅ Install Scripts (Pro) |
| **CI/CD workaround** | N/A (native) | N/A (native) | SSH + cron jobs | SSH + cron jobs | SSH/SFTP + cron | SSH + cron jobs |

#### CI/CD Deep Dive

**Coolify** offers the most comprehensive Git deployment story. It connects directly to GitHub (as a GitHub App), GitLab, Bitbucket, and Gitea. On push, it automatically builds and deploys. PR preview deployments create separate environments for each pull request. A full REST API enables programmatic control. The [coolify-cli](https://github.com/coollabsio/coolify-cli) provides terminal access. Webhooks allow integration with any external CI/CD pipeline (GitHub Actions, GitLab CI, etc.).

- [Coolify webhook docs](https://coolify.io/docs/)
- [Coolify API reference](https://coolify.io/docs/api-reference)

**CapRover** uses a community-maintained [GitHub Action](https://github.com/caprover/deploy-from-github) for CI/CD. The workflow builds on GitHub's runners (saving server resources), pushes to a container registry, then deploys to CapRover via its webhook API. CapRover also has a `caprover deploy` CLI that pushes the current git commit to the server. Per-app tokens provide scoped authentication.

- [CapRover GitHub deploy guide](https://caprover.com/docs/ci-cd-integration/deploy-from-github.html)
- [CapRover CLI docs](https://caprover.com/docs/get-started.html)

**HestiaCP** has a full REST API (enabled by default with `--api yes`) and ~150+ `v-*` CLI commands for managing domains, users, databases, etc. However, there is no built-in Git integration or webhook endpoint. CI/CD requires an external pipeline (e.g., GitHub Actions) that SSH/SCPs files to the server and uses `v-*` commands to manage the hosting configuration.

- [HestiaCP CLI reference](https://docs.hestiacp.com/docs/server-administration/rest-api.html)

**CloudPanel** has **no API, no CLI, no webhook, no Git deploy, and no Docker support**. Deployment is exclusively via SSH/SFTP file transfer. Any automation requires scripting around SSH. This is the most limited panel for CI/CD.

- [CloudPanel docs](https://www.cloudpanel.io/docs/v2/getting-started/)

**CyberPanel** has a management CLI and a limited API, but no native Git deployment or webhook support. Docker container management exists but is separate from the web hosting workflow. CI/CD requires SSH-based scripts.

- [CyberPanel GitHub](https://github.com/usmannasir/cyberpanel)

**Virtualmin** provides a comprehensive CLI (`virtualmin` command) and HTTP API inherited from Webmin. Pro version includes "Install Scripts" for one-click app deployment (WordPress, etc.). No Git integration or webhooks. CI/CD via SSH + API calls.

- [Virtualmin documentation](https://www.virtualmin.com/docs/)
- [Virtualmin Professional features](https://www.virtualmin.com/professional-features/)

### Security

| Feature | Coolify | CapRover | HestiaCP | CyberPanel | CloudPanel | Virtualmin |
|---------|---------|----------|----------|------------|------------|------------|
| **Firewall** | Server-level | Docker + UFW | iptables + Fail2Ban | FirewallD | UFW | iptables + Fail2Ban |
| **Let's Encrypt SSL** | ✅ Auto | ✅ Auto | ✅ Auto + wildcard | ✅ Auto | ✅ Auto | ✅ Auto |
| **2FA** | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ (Webmin) |
| **Anti-virus** | ❌ | ❌ | ✅ ClamAV | ✅ AI Scanner | ❌ | ✅ ClamAV |
| **Anti-spam** | ❌ | ❌ | ✅ SpamAssassin | ✅ SpamAssassin | ❌ | ✅ SpamAssassin |

#### Known Security Vulnerabilities (CVEs)

| Panel | CVE | Severity | Description | Fixed |
|-------|-----|----------|-------------|-------|
| **CloudPanel** | [CVE-2023-35885](https://nvd.nist.gov/vuln/detail/CVE-2023-35885) | Critical (9.8) | Unauthenticated RCE via crafted request | Yes (v2.3.1+) |
| **CyberPanel** | [CVE-2024-51567](https://nvd.nist.gov/vuln/detail/CVE-2024-51567) | Critical (9.8) | Pre-auth RCE, **actively exploited in the wild** | Yes (v2.3.8+) |
| **CyberPanel** | [CVE-2024-51568](https://nvd.nist.gov/vuln/detail/CVE-2024-51568) | High (8.8) | Command injection via file manager | Yes (v2.3.8+) |
| **HestiaCP** | — | — | No critical CVEs on record | N/A |
| **Coolify** | — | — | No critical CVEs on record | N/A |
| **CapRover** | — | — | No critical CVEs on record | N/A |
| **Virtualmin** | — | — | No critical CVEs on record (Webmin has had some historical ones, all patched) | N/A |

**Sources**: [NVD CVE Database](https://nvd.nist.gov/), [CloudPanel CVE-2023-35885](https://nvd.nist.gov/vuln/detail/CVE-2023-35885), [CyberPanel CVE-2024-51567](https://nvd.nist.gov/vuln/detail/CVE-2024-51567)

---

## Company & Sustainability Assessment

Long-term viability matters for infrastructure tooling. Here's what backs each project:

### Coolify

- **Founder**: Andras Bacsai (solo founder, full-time on Coolify)
- **Revenue model**: Coolify Cloud ($5/mo per server) — 3,100+ paying customers as of 2026
- **Community**: 16,000+ Discord members, 204,000+ self-hosted instances claimed
- **Governance**: Single-founder project with active development (commits daily)
- **Risk**: Bus-factor risk (one founder), but strong community adoption and commercial revenue provide sustainability. Apache 2.0 license means community can fork if needed.
- **Track record**: Founded ~2022, rapid growth trajectory. Most actively developed panel.
- [Coolify GitHub](https://github.com/coollabsio/coolify)

### CapRover

- **Founder**: Originally by Kasra Madadipouya
- **Revenue model**: Donations only (Open Collective)
- **Community**: Strong initial adoption, but development has slowed noticeably
- **Governance**: Community-driven, multiple contributors
- **Risk**: No commercial backing. Last commit Jan 2026 but release cadence has slowed. Functional and stable but unlikely to gain major new features.
- **Track record**: Founded ~2018, mature and stable. Docker Swarm architecture is proven.
- [CapRover GitHub](https://github.com/caprover/caprover)

### HestiaCP

- **Founded**: 2018, community fork of VestaCP after VestaCP's security and governance concerns
- **Revenue model**: Donations (PayPal, crypto)
- **Community**: Multi-maintainer team (5+ active), well-organized GitHub project
- **Governance**: **Best governance model** of all candidates — multiple core maintainers, structured release process, active issue triage
- **Risk**: Lowest risk for a donation-funded project due to distributed maintainership. Traditional hosting panel without modern PaaS features.
- **Track record**: 6+ years of consistent releases. Fork origin story demonstrates community's ability to self-organize.
- [HestiaCP GitHub](https://github.com/hestiacp/hestiacp)

### CyberPanel

- **Founder**: Usman Nasir (single maintainer)
- **Revenue model**: Paid add-ons, support plans, 7-day free trial model
- **Community**: Small contributor base, most commits from single maintainer
- **Governance**: Single-person project with paid add-on model
- **Risk**: **Highest risk** — single maintainer, critical CVEs actively exploited in 2024, x86-only limitation. The paid add-on model with refund restrictions suggests commercial pressure.
- **Track record**: Tied to OpenLiteSpeed (LiteSpeed Technologies). If LiteSpeed deprioritizes the project, maintenance could stall.
- [CyberPanel GitHub](https://github.com/usmannasir/cyberpanel)

### CloudPanel

- **Founder**: MGT-Commerce GmbH (small Austrian company)
- **Revenue model**: Unclear — no paid tier, no cloud offering. Company revenue likely comes from other products.
- **Community**: Small (1.8K stars), limited contributor diversity
- **Governance**: Corporate-controlled, closed development process
- **Risk**: **High risk** — last commit September 2025 (5 months stale as of Feb 2026), no apparent revenue from the panel itself, small company, critical CVE history. OCI has official CloudPanel images, which provides some validation.
- **Track record**: MIT licensed, but closed development style. If company deprioritizes, project dies.
- [CloudPanel GitHub](https://github.com/cloudpanel-io/cloudpanel-ce)

### Virtualmin

- **Founded**: 2003 (based on Webmin, which dates to 1997)
- **Revenue model**: Virtualmin Pro at $7.50/month — sustainable commercial model
- **Company**: Virtualmin Inc., run by Jamie Cameron (Webmin creator) and Joe Cooper
- **Governance**: Small but stable team, 20+ year track record
- **Risk**: **Lowest overall risk** — longest track record, proven commercial model, small but dedicated team. Traditional panel without modern PaaS features.
- **Track record**: 20+ years. Has survived multiple generations of hosting trends. Webmin is one of the oldest web-based admin tools in existence.
- [Virtualmin documentation](https://www.virtualmin.com/docs/)
- [Webmin GitHub](https://github.com/webmin/webmin)

---

## Use-Case Fit Matrix

For deploying hobby websites, backends, and middleware with Git CI/CD and Docker:

| Criterion | Coolify | CapRover | HestiaCP | CyberPanel | CloudPanel | Virtualmin |
|-----------|---------|----------|----------|------------|------------|------------|
| **Git CI/CD** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ✗ | ⭐ |
| **Docker** | ⭐⭐⭐ | ⭐⭐⭐ | ✗ | ⭐⭐ | ✗ | ✗ |
| **ARM64 support** | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **1 GB RAM viable** | ❌ (needs 2 GB) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Traditional hosting** | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **API/automation** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ✗ | ⭐⭐⭐ |
| **Long-term viability** | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ |
| **OCI free-tier fit** | ⚠️ ARM only | ✅ | ✅ | ❌ x86 only | ✅ | ✅ |
| **Security record** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ |

### Key Considerations for OCI Free Tier

- **x86 E2.1.Micro** (1 OCPU, 1 GB RAM): Rules out Coolify (needs 2 GB). CyberPanel is x86-only so it would only run here.
- **ARM A1.Flex** (up to 4 OCPU, 24 GB RAM): Best fit for Coolify. All panels except CyberPanel support ARM64.
- **Multi-VM**: If using multiple VMs, Coolify can manage deployments to remote servers over SSH from a central instance.

---

## Summary by Archetype

### "I want Vercel/Heroku but self-hosted" → **Coolify** or **CapRover**

Both are PaaS-style platforms built on Docker with Git push-to-deploy. Coolify has richer features (PR previews, multi-Git-provider support, full API, 280+ one-click services) but needs 2 GB RAM minimum. CapRover is lighter, uses Docker Swarm for clustering, and has a proven `caprover deploy` CLI, but development has slowed.

### "I want traditional cPanel-style hosting" → **HestiaCP** or **Virtualmin**

Both offer multi-domain web hosting with DNS, email, databases, and firewall management. HestiaCP has the best community governance and a modern UI. Virtualmin has a 20+ year track record and a sustainable commercial model (Pro at $7.50/mo). Neither has native Git/Docker CI/CD.

### "I want the lowest risk, longest track record" → **Virtualmin**

Twenty years of continuous development, a stable commercial model, and the smallest resource footprint (256 MB RAM minimum). Trade-off: no modern PaaS features.

### "I need to avoid" → **CyberPanel** (security), **CloudPanel** (stale development)

CyberPanel had critical CVEs actively exploited in the wild (2024) and is single-maintainer, x86-only. CloudPanel's last commit was 5 months ago with no visible revenue model to sustain development.

---

## References

### Official Documentation

- Coolify: [coolify.io/docs](https://coolify.io/docs/)
- CapRover: [caprover.com/docs](https://caprover.com/docs/get-started.html)
- HestiaCP: [docs.hestiacp.com](https://docs.hestiacp.com/docs/introduction/getting-started.html)
- CyberPanel: [cyberpanel.net](https://cyberpanel.net/) | [GitHub](https://github.com/usmannasir/cyberpanel)
- CloudPanel: [cloudpanel.io/docs](https://www.cloudpanel.io/docs/v2/getting-started/)
- Virtualmin: [virtualmin.com/docs](https://www.virtualmin.com/docs/) | [Professional features](https://www.virtualmin.com/professional-features/)

### GitHub Repositories

- [coollabsio/coolify](https://github.com/coollabsio/coolify)
- [caprover/caprover](https://github.com/caprover/caprover)
- [hestiacp/hestiacp](https://github.com/hestiacp/hestiacp)
- [usmannasir/cyberpanel](https://github.com/usmannasir/cyberpanel)
- [cloudpanel-io/cloudpanel-ce](https://github.com/cloudpanel-io/cloudpanel-ce)
- [webmin/webmin](https://github.com/webmin/webmin)

### CI/CD Integration Guides

- [CapRover + GitHub Actions](https://caprover.com/docs/ci-cd-integration/deploy-from-github.html)
- [CapRover deploy GitHub Action](https://github.com/caprover/deploy-from-github)
- [Coolify webhooks & API](https://coolify.io/docs/)
- [Coolify CLI](https://github.com/coollabsio/coolify-cli)

### Security

- [NVD CVE Database](https://nvd.nist.gov/)
- [CVE-2023-35885 (CloudPanel)](https://nvd.nist.gov/vuln/detail/CVE-2023-35885)
- [CVE-2024-51567 (CyberPanel)](https://nvd.nist.gov/vuln/detail/CVE-2024-51567)
