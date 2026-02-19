# How to Generate an OCI API Signing Key

This guide walks you through generating the API signing key needed to authenticate OCI CLI commands. The key pair will be stored in your local (gitignored) directory.

## Prerequisites

- An Oracle Cloud Infrastructure account
- OpenSSL installed (`openssl version` to verify)
- OCI CLI installed (`oci --version` to verify)

## Step 1: Create the Local Directory

```bash
# From the repo root
mkdir -p oci/local/api-keys
```

## Step 2: Generate the API Key Pair

```bash
# Generate a 2048-bit RSA private key
openssl genrsa -out oci/local/api-keys/oci_api_key.pem 2048

# Set restrictive permissions
chmod 600 oci/local/api-keys/oci_api_key.pem

# Generate the public key from the private key
openssl rsa -pubout -in oci/local/api-keys/oci_api_key.pem \
  -out oci/local/api-keys/oci_api_key_public.pem
```

## Step 3: Get the Key Fingerprint

```bash
openssl rsa -pubout -outform DER \
  -in oci/local/api-keys/oci_api_key.pem 2>/dev/null | \
  openssl md5 -c | awk '{print $2}'
```

Save this fingerprint — you'll need it for the config file.

## Step 4: Upload the Public Key to OCI Console

1. Log in to the [OCI Console](https://cloud.oracle.com/)
2. Click your **Profile icon** (top-right) → **My Profile** (or **User Settings**)
3. Scroll down to **API Keys** → click **Add API Key**
4. Select **Paste Public Key**
5. Paste the contents of `oci/local/api-keys/oci_api_key_public.pem`:
   ```bash
   cat oci/local/api-keys/oci_api_key_public.pem
   ```
6. Click **Add**
7. OCI will display a **Configuration File Preview** — save this info for the next step

## Step 5: Create Your OCI Config File

```bash
# Copy the template
cp oci/templates/oci-config.template oci/local/config/oci-config

# Edit with your values from the OCI Console
nano oci/local/config/oci-config
```

Fill in the values from the Configuration File Preview shown in Step 4:

```ini
[DEFAULT]
user=ocid1.user.oc1..xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
fingerprint=aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99
tenancy=ocid1.tenancy.oc1..xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
region=us-ashburn-1
key_file=oci/local/api-keys/oci_api_key.pem
```

## Step 6: Verify the Configuration

```bash
# Test with a simple API call
oci iam region list --config-file oci/local/config/oci-config
```

If successful, you'll see a JSON list of OCI regions.

## How to Find Your OCIDs

| Value | Where to find it |
|-------|-----------------|
| **User OCID** | OCI Console → Profile → My Profile → OCID (click "Copy") |
| **Tenancy OCID** | OCI Console → Profile → Tenancy: `<name>` → OCID (click "Copy") |
| **Compartment OCID** | OCI Console → Identity → Compartments → select compartment → OCID |
| **Region** | Shown in the top bar of the OCI Console (e.g., `us-ashburn-1`) |

## Security Notes

- **NEVER** commit `oci/local/` to git — it is gitignored
- The private key (`oci_api_key.pem`) is the most sensitive file — protect it
- If you suspect a key is compromised, delete it from the OCI Console immediately and generate a new one
- You can have up to 3 API keys per user in OCI
