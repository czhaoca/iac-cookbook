# CLAUDE.md — AI Assistant Rules for Nimbus

## Project Identity

**Nimbus** is a personal multi-cloud orchestration platform with:
- **Engine** (Python/FastAPI) — backend API + CLI for provisioning, monitoring, budget enforcement
- **UI** (React/Vite) — frontend dashboard for observability and actions
- **Providers** — OCI, Azure, GCP, AWS, Cloudflare, Proxmox adapters
- **Mono-repo** now (`nimbus`); future split: `nimbus-core` + `nimbus-ui`

## ⚠️ CRITICAL: Pre-Commit Security Checklist

Before ANY `git add`, `git commit`, or `git push`, you MUST:

1. **Scan all staged files** for secrets, tokens, and credentials:
   ```bash
   git diff --cached --name-only | xargs grep -nEi \
     'BEGIN (RSA|PRIVATE|EC|OPENSSH) KEY|password\s*=|token\s*=|secret\s*=|api[_-]?key\s*=|ocid[0-9]|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36}|sk-[A-Za-z0-9]{48}'
   ```
2. **If ANY match is found**: STOP. Remove the secret. Refactor the code to read from a `local/` config file instead.
3. **Verify no `local/` directories are staged**:
   ```bash
   git diff --cached --name-only | grep '/local/'
   ```
   If any results appear, unstage them immediately: `git reset HEAD <file>`

## Secret Decoupling Rules

1. **NEVER hardcode** secrets, tokens, passwords, OCIDs, API keys, or private IPs in scripts or config files that are committed to the repo.
2. **ALWAYS use the `local/` convention**: each cloud provider directory has a `local/` subdirectory (e.g., `oci/local/`) that is gitignored. Store all user-specific secrets there.
3. **ALWAYS provide templates**: for every config file in `local/`, provide a corresponding `.template` file in `templates/` with placeholder values and comments explaining what to fill in.
4. **When writing scripts**: read secrets from config files in `local/`, environment variables, or CLI prompts — never embed them.
5. **When providing solutions**: always parameterize secrets. Reference the `local/` config file path. Show the user how to copy the template and fill in their values.
6. **NEVER expose infrastructure naming conventions** (instance names, hostnames, region-prefixed identifiers, domain patterns, or any naming scheme that could reveal the owner's infrastructure topology). In public-facing docs or scripts, use generic placeholders like `vm-arm-1`, `vm-x86-1`, `my-instance`, etc. Real names belong in `local/` config files only.

## File Structure Convention

```
<provider>/
├── scripts/        # Public scripts (committed) — NO secrets
├── templates/      # Config templates with placeholders (committed)
├── docs/           # Documentation (committed)
└── local/          # User-specific secrets & config (GITIGNORED)
    ├── api-keys/   # API signing keys
    ├── ssh/        # SSH keys for instances
    ├── config/     # Instance configs, credentials
    └── logs/       # Operation logs
```

## Patterns to Scan For

Before committing, grep for these patterns — any match is a potential leak:

| Pattern | What it catches |
|---------|----------------|
| `BEGIN.*PRIVATE KEY` | PEM private keys |
| `ocid1\.[a-z]+\.oc1\.` | OCI resource OCIDs |
| `AKIA[A-Z0-9]{16}` | AWS access key IDs |
| `ghp_[A-Za-z0-9]{36}` | GitHub personal access tokens |
| `sk-[A-Za-z0-9]{48}` | OpenAI / Stripe secret keys |
| `password\s*=\s*\S+` | Hardcoded passwords |
| `token\s*=\s*\S+` | Hardcoded tokens |
| `secret\s*=\s*\S+` | Hardcoded secrets |
| `10\.\d+\.\d+\.\d+` | Private IP addresses |
| `172\.(1[6-9]\|2[0-9]\|3[01])\.\d+\.\d+` | Private IP addresses |
| `192\.168\.\d+\.\d+` | Private IP addresses |

## Code Generation Rules

- When generating shell scripts, always use `source` or config file reads for credentials
- Default config path: `$(dirname "$0")/../local/config/<config-file>`
- Always check if config file exists before sourcing; print helpful error if missing
- Provide `--help` output in every script
- Include dry-run mode for destructive operations
- **ALWAYS reference latest official documentation** when implementing features; do not use deprecated or soon-to-be-deprecated functions, packages, or APIs
- When choosing package versions, prefer **latest stable release** (not beta/RC); pin exact major versions to avoid breaking changes
- If a package has known CVEs, document the risk and either upgrade to a patched version or choose an alternative

## Architecture Decision Records

Save architectural analysis and decision records in `docs/` to document **why** we choose specific cloud architectures, tools, and patterns:

```
docs/
├── <provider>/
│   └── architecture/    # Cloud architecture decisions (storage, networking, compute)
├── control-panels/      # Control panel comparison and selection rationale
└── <topic>/             # Other cross-cutting decisions
```

- Each document should include: problem statement, options considered, decision rationale, trade-offs, and **links to official docs** so readers can verify and dive deeper.
- Ground-check all claims against official documentation — do not rely on assumptions.
- These docs are committed to the repo so contributors (and forks) understand the reasoning behind infrastructure choices.

## Iteration & Dev History Tracking

### Conversation History

Every AI-assisted development session MUST create a summary file:

```
local/dev-history/0.0.X-short-description.md
```

- **Location**: `local/dev-history/` (GITIGNORED — never committed)
- **Numbering**: `0.0.N` auto-increments with each session. Do NOT increment to `0.1.0` unless explicitly instructed by the user.
- **Content template**:
  ```markdown
  # 0.0.X — Short Description
  **Date**: YYYY-MM-DD
  **Summary**: One-paragraph overview of what was accomplished.
  ## Key Decisions
  - Decision 1
  - Decision 2
  ## Files Changed
  - file1.py — what changed
  - file2.md — what changed
  ## Next Steps
  - What's queued for the next session
  ```

### Roadmap Updates

Every session MUST update the roadmap in plan.md or README.md:
- Check off completed items
- Add newly discovered items
- Re-prioritize if scope changed

### Scrum-Style Recap

Before wrapping up ANY session, the AI MUST interactively discuss:
1. **What was done** — bullet list of completed work
2. **What's blocked** — any blockers or decisions needed
3. **What's next** — top 3 priorities for the next session
4. **Realignment** — ask the user if priorities should change

This is mandatory. Do NOT end a session without this recap.

## Resource Naming & Collision Prevention

- All cloud resources MUST use a configurable prefix from the user's config: `{prefix}-{type}-{label}-{seq}`
- Examples: `prod-vm-arm-01`, `dev-dns-api`, `staging-vol-data-01`
- Before creating ANY named resource:
  1. Query the local database for existing names with the same prefix
  2. For DNS records: check the DNS provider API for subdomain existence
  3. If collision detected: auto-increment sequence number or prompt user
- Prefix configuration lives in `local/config/` (gitignored)
- Templates in `templates/` use generic placeholders: `{prefix}`, `my-resource`, etc.

## Database Schema Rules

- Primary database: **SQLite** (file in `local/data/nimbus.db`)
- ORM: **SQLAlchemy** with **Alembic** migrations
- If a future Postgres deployment is added:
  - Both SQLite and Postgres schema MUST be kept in sync
  - Use Alembic migrations that are dialect-compatible
  - Test migrations against both databases before committing
  - Document any dialect-specific SQL in comments

## Iteration Cycle SOP

Every trunk/phase completion MUST follow this quality cycle:

1. **Implement** — Write the feature code
2. **Quality Review** — Act as quality engineer:
   - Identify tightly-coupled components that should be decoupled
   - Extract reusable abstractions into shared interfaces
   - Refactor existing code to use the new abstractions (don't leave dead code)
   - Verify folder structure is clean (move misplaced files)
3. **Test** — Run all existing tests to ensure nothing is broken
4. **Docs** — Update documentation and fix broken links/references
5. **Security Scan** — Run the pre-commit secret scan
6. **Commit** — Commit with descriptive message + Co-authored-by trailer

This cycle applies to every meaningful unit of work (feature, refactor, bugfix).
Do NOT skip the quality review step — it prevents tech debt accumulation.

## Docker & Deployment

- Engine and UI run as **separate Docker containers**
- `docker-compose.yml` at repo root for development
- `deploy/` directory for production configs, Proxmox scripts, Nginx configs
- Database file (SQLite) is mounted as a Docker volume from `local/data/`
- Credentials mounted from `local/config/` — NEVER baked into Docker images

## CI/CD & Security Scanning

- **GitHub Actions** runs on every push/PR: lint, test, build, security scan
- **Dependabot** enabled for npm and pip ecosystems — auto-creates PRs for vulnerable dependencies
- **CodeQL** analysis runs on push to `main` and weekly schedule to detect code-level vulnerabilities
- **npm audit** and **pip-audit** run in CI to catch known CVEs in dependencies
- Any HIGH or CRITICAL severity CVE MUST be addressed before merging to main
- Vite/React ecosystem has had critical CVEs (server-side request forgery, path traversal) — always run on latest patched stable version
- Production builds MUST NOT expose Vite dev server; use `vite build` + static file serving (Nginx)
- Frontend MUST be served behind a reverse proxy with security headers (CSP, HSTS, X-Frame-Options)
