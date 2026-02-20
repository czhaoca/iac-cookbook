# How to Set Up OCI API Access

This guide covers all methods to authenticate the OCI CLI for use with the reprovisioning script.

## Quick Start

The **easiest way** is to run the reprovisioning script — it will guide you interactively:

```bash
./oci/scripts/reprovision-vm.sh
```

The script detects existing profiles in `~/.oci/config`, lets you choose one, or walks you through creating a new one.

## Multi-Profile Support

OCI CLI supports multiple profiles in a single config file (`~/.oci/config`). Each profile can connect to a different tenancy, region, or user.

```ini
# ~/.oci/config

[DEFAULT]
user=ocid1.user.oc1..aaaaaa_default_user
tenancy=ocid1.tenancy.oc1..aaaaaa_default_tenancy
region=us-ashburn-1
key_file=~/.oci/keys/DEFAULT/oci_api_key.pem
fingerprint=aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99

[PROD]
user=ocid1.user.oc1..aaaaaa_prod_user
tenancy=ocid1.tenancy.oc1..aaaaaa_prod_tenancy
region=ca-toronto-1
key_file=~/.oci/keys/PROD/oci_api_key.pem
fingerprint=11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00
```

Use with the script:

```bash
# Interactive — script lists profiles and lets you choose
./oci/scripts/reprovision-vm.sh

# Specify profile via flag
./oci/scripts/reprovision-vm.sh --profile PROD

# Dry run with specific profile
./oci/scripts/reprovision-vm.sh --profile DEV --dry-run
```

### Key Storage

API keys are organized per profile under `~/.oci/keys/`:

```
~/.oci/
├── config                    # Multi-profile config file
└── keys/
    ├── DEFAULT/
    │   ├── oci_api_20250220.pem        # Private key
    │   └── oci_api_20250220_public.pem # Public key
    └── PROD/
        ├── oci_api_20250220.pem
        └── oci_api_20250220_public.pem
```

---

## Authentication Methods

When adding a new profile, the script offers three methods:

| Method | Best For | What It Does |
|--------|----------|-------------|
| **Browser Login** | Easiest setup | Opens browser, auto-generates & uploads keys |
| **Interactive CLI** | No browser / SSH-only | Step-by-step prompts for OCIDs + key generation |
| **Existing Credentials** | Already have OCIDs & key | Enter values directly, key copied to profile dir |

---

## Method 1: Browser Login (`oci setup bootstrap`)

The simplest method — opens a browser for OCI login and handles everything automatically.

```bash
# The reprovision script offers this as option 1, or run directly:
oci setup bootstrap
```

**Requirements**: Web browser accessible from this machine, port 8181 available.

---

## Method 2: Interactive CLI Setup (Step-by-Step)

For headless servers or when you prefer manual control.

### Prerequisites

- An Oracle Cloud Infrastructure account
- OpenSSL installed (`openssl version` to verify)
- OCI CLI installed (`oci --version` to verify)

### What You'll Need

Before starting, gather these values from the [OCI Console](https://cloud.oracle.com/):

| Value | Where to Find It |
|-------|-----------------|
| **User OCID** | Profile icon (top-right) → **User Settings** → OCID → Copy |
| **Tenancy OCID** | Profile icon → **Tenancy: \<name\>** → OCID → Copy |
| **Region** | Shown in the top bar (e.g., `us-ashburn-1`, `ca-toronto-1`) |

### Step-by-Step (Manual)

#### 1. Generate the API Key Pair

```bash
mkdir -p ~/.oci/keys/DEFAULT
openssl genrsa -out ~/.oci/keys/DEFAULT/oci_api_key.pem 2048
chmod 600 ~/.oci/keys/DEFAULT/oci_api_key.pem
openssl rsa -pubout -in ~/.oci/keys/DEFAULT/oci_api_key.pem \
  -out ~/.oci/keys/DEFAULT/oci_api_key_public.pem
```

#### 2. Get the Key Fingerprint

```bash
openssl rsa -pubout -outform DER \
  -in ~/.oci/keys/DEFAULT/oci_api_key.pem 2>/dev/null | \
  openssl md5 -c | awk '{print $2}'
```

#### 3. Upload the Public Key to OCI Console

1. Log in to [cloud.oracle.com](https://cloud.oracle.com/)
2. Click **Profile icon** (top-right) → **User Settings**
3. Go to **Tokens and keys** (under Resources, left sidebar)
4. Click **Add API Key**
5. Select **Paste a Public Key**
6. Paste the contents of the public key:
   ```bash
   cat ~/.oci/keys/DEFAULT/oci_api_key_public.pem
   ```
7. Click **Add**

#### 4. Create Your OCI Config File

```bash
cat > ~/.oci/config <<EOF
[DEFAULT]
user=ocid1.user.oc1..YOUR_USER_OCID
fingerprint=YOUR_KEY_FINGERPRINT
tenancy=ocid1.tenancy.oc1..YOUR_TENANCY_OCID
region=us-ashburn-1
key_file=~/.oci/keys/DEFAULT/oci_api_key.pem
EOF
chmod 600 ~/.oci/config
```

#### 5. Verify the Configuration

```bash
oci iam region list --output table
```

If successful, you'll see a table of OCI regions.

---

## Method 3: Use Existing Credentials

If you already have `~/.oci/config` from a previous `oci setup config`, the script will detect it automatically. Just run the script and select your profile.

To add a profile manually:

```bash
cat >> ~/.oci/config <<EOF

[PROD]
user=ocid1.user.oc1..YOUR_USER_OCID
fingerprint=YOUR_KEY_FINGERPRINT
tenancy=ocid1.tenancy.oc1..YOUR_TENANCY_OCID
region=ca-toronto-1
key_file=~/.oci/keys/PROD/oci_api_key.pem
EOF
```

---

## Troubleshooting

| Error | Solution |
|-------|---------|
| `401 - NotAuthenticated` | API key not uploaded, or fingerprint mismatch. Re-upload the public key. |
| `404 - NotAuthorizedOrNotFound` | User/Tenancy OCID is wrong. Verify in OCI Console. |
| `Could not find config file` | Check file exists: `ls ~/.oci/config` |
| `Private key file not found` | Check `key_file=` path in config. Use absolute path. |
| `Invalid key` | Key was corrupted. Re-generate with `openssl genrsa`. |
| Profile not found | Run `grep '^\[' ~/.oci/config` to see available profiles. |

## Security Notes

- **NEVER** commit private keys or `~/.oci/config` to git
- The repo's `oci/local/` directory is gitignored for any local config copies
- API keys in `~/.oci/keys/` are outside the repo — safe by default
- If you suspect a key is compromised, delete it from the OCI Console immediately
- You can have up to 3 API keys per user in OCI
- When forking this repo, ensure your fork's `.gitignore` keeps secrets excluded
