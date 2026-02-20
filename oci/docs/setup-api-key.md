# How to Set Up OCI API Access

This guide covers all methods to authenticate the OCI CLI for use with the reprovisioning script.

## Quick Start

The **easiest way** is to run the reprovisioning script — it will guide you interactively:

```bash
./oci/scripts/reprovision-vm.sh
```

The script offers three authentication methods:

| Method | Best For | What It Does |
|--------|----------|-------------|
| **Browser Login** | Easiest setup | Opens browser, auto-generates & uploads keys |
| **Interactive CLI** | No browser / SSH-only | Step-by-step prompts for OCIDs + key generation |
| **Existing Config** | Already have `~/.oci/config` | Copies your existing config |

---

## Method 1: Browser Login (`oci setup bootstrap`)

The simplest method — opens a browser for OCI login and handles everything automatically.

```bash
# The reprovision script offers this as option 1, or run directly:
oci setup bootstrap --config-location oci/local/config/oci-config
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
| **Region** | Shown in the top bar (e.g., `us-ashburn-1`) |

### Step-by-Step

#### 1. Create the Local Directory

```bash
mkdir -p oci/local/config oci/local/api-keys
```

#### 2. Generate the API Key Pair

**Option A — Use OCI CLI** (recommended):
```bash
oci setup keys --output-dir oci/local/api-keys --key-name oci_api_key
```

**Option B — Use OpenSSL**:
```bash
openssl genrsa -out oci/local/api-keys/oci_api_key.pem 2048
chmod 600 oci/local/api-keys/oci_api_key.pem
openssl rsa -pubout -in oci/local/api-keys/oci_api_key.pem \
  -out oci/local/api-keys/oci_api_key_public.pem
```

#### 3. Get the Key Fingerprint

```bash
openssl rsa -pubout -outform DER \
  -in oci/local/api-keys/oci_api_key.pem 2>/dev/null | \
  openssl md5 -c | awk '{print $2}'
```

Save this fingerprint — you'll need it for the config file.

#### 4. Upload the Public Key to OCI Console

1. Log in to [cloud.oracle.com](https://cloud.oracle.com/)
2. Click **Profile icon** (top-right) → **User Settings**
3. Go to **Tokens and keys** (under Resources, left sidebar)
4. Click **Add API Key**
4. Select **Paste a Public Key**
5. Paste the contents of the public key:
   ```bash
   cat oci/local/api-keys/oci_api_key_public.pem
   ```
6. Click **Add**
7. OCI will show a **Configuration File Preview** — you can verify your values match

#### 5. Create Your OCI Config File

```bash
cp oci/templates/oci-config.template oci/local/config/oci-config
nano oci/local/config/oci-config
```

Fill in your values:

```ini
[DEFAULT]
user=ocid1.user.oc1..xxxxxxxxxxxxxxxxxxxxxxxxxxxx
fingerprint=aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99
tenancy=ocid1.tenancy.oc1..xxxxxxxxxxxxxxxxxxxxxxxxxxxx
region=us-ashburn-1
key_file=oci/local/api-keys/oci_api_key.pem
```

#### 6. Verify the Configuration

```bash
oci --config-file oci/local/config/oci-config iam region list --output table
```

If successful, you'll see a table of OCI regions.

---

## Method 3: Use Existing Config

If you already have `~/.oci/config` from a previous `oci setup config`:

```bash
mkdir -p oci/local/config
cp ~/.oci/config oci/local/config/oci-config
```

Make sure the `key_file` path in the copied config is still valid (use absolute path).

---

## Troubleshooting

| Error | Solution |
|-------|---------|
| `401 - NotAuthenticated` | API key not uploaded, or fingerprint mismatch. Re-upload the public key. |
| `404 - NotAuthorizedOrNotFound` | User/Tenancy OCID is wrong. Verify in OCI Console. |
| `Could not find config file` | Check file path: `oci/local/config/oci-config` |
| `Private key file not found` | Check `key_file=` path in config. Use absolute path if needed. |
| `Invalid key` | Key was corrupted. Re-generate with `oci setup keys`. |

## Security Notes

- **NEVER** commit `oci/local/` to git — it is gitignored
- The private key (`oci_api_key.pem`) is the most sensitive file — protect it
- If you suspect a key is compromised, delete it from the OCI Console immediately
- You can have up to 3 API keys per user in OCI
