"""OCI authentication — profile management, SDK client factory, connectivity test."""

from __future__ import annotations

import configparser
import os
import subprocess
from pathlib import Path
from typing import Optional

import oci

from .common import (
    confirm,
    console,
    die,
    log,
    print_detail,
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
    print_warning,
    prompt_input,
    prompt_selection,
)
from .config import ReprovisionConfig

# ---------------------------------------------------------------------------
# OCI config file helpers
# ---------------------------------------------------------------------------

OCI_CONFIG_PATH = Path.home() / ".oci" / "config"


def list_profiles() -> list[str]:
    """Return profile names from ~/.oci/config."""
    if not OCI_CONFIG_PATH.is_file():
        return []
    cp = configparser.ConfigParser()
    cp.read(OCI_CONFIG_PATH)
    return list(cp.sections())


def get_profile_value(profile: str, key: str) -> str:
    """Read a single value from a profile section."""
    cp = configparser.ConfigParser()
    cp.read(OCI_CONFIG_PATH)
    return cp.get(profile, key, fallback="")


# ---------------------------------------------------------------------------
# SDK client factory
# ---------------------------------------------------------------------------

class OCIClients:
    """Lazily-initialised container for all OCI service clients."""

    def __init__(self, profile: str):
        self.profile = profile
        self._config: Optional[dict] = None
        self._compute: Optional[oci.core.ComputeClient] = None
        self._blockstorage: Optional[oci.core.BlockstorageClient] = None
        self._vnet: Optional[oci.core.VirtualNetworkClient] = None
        self._identity: Optional[oci.identity.IdentityClient] = None
        self._limits: Optional[oci.limits.LimitsClient] = None

    @property
    def config(self) -> dict:
        if self._config is None:
            self._config = oci.config.from_file(
                file_location=str(OCI_CONFIG_PATH),
                profile_name=self.profile,
            )
            oci.config.validate_config(self._config)
        return self._config

    @property
    def compute(self) -> oci.core.ComputeClient:
        if self._compute is None:
            self._compute = oci.core.ComputeClient(self.config)
        return self._compute

    @property
    def blockstorage(self) -> oci.core.BlockstorageClient:
        if self._blockstorage is None:
            self._blockstorage = oci.core.BlockstorageClient(self.config)
        return self._blockstorage

    @property
    def vnet(self) -> oci.core.VirtualNetworkClient:
        if self._vnet is None:
            self._vnet = oci.core.VirtualNetworkClient(self.config)
        return self._vnet

    @property
    def identity(self) -> oci.identity.IdentityClient:
        if self._identity is None:
            self._identity = oci.identity.IdentityClient(self.config)
        return self._identity

    @property
    def limits(self) -> oci.limits.LimitsClient:
        if self._limits is None:
            self._limits = oci.limits.LimitsClient(self.config)
        return self._limits


# ---------------------------------------------------------------------------
# Connectivity test
# ---------------------------------------------------------------------------

def test_connectivity(clients: OCIClients) -> str:
    """Test API connectivity by listing regions. Returns home region name."""
    try:
        resp = clients.identity.list_region_subscriptions(
            clients.config["tenancy"]
        )
        home = next(
            (r.region_name for r in resp.data if r.is_home_region), ""
        )
        return home or clients.config.get("region", "unknown")
    except oci.exceptions.ServiceError as exc:
        die(f"OCI API connectivity failed: {exc.message}")
    return ""


# ---------------------------------------------------------------------------
# Interactive profile selection / setup
# ---------------------------------------------------------------------------

def select_profile(cfg: ReprovisionConfig) -> OCIClients:
    """Interactively select or set up an OCI profile. Returns initialised clients."""
    print_header("OCI Profile & Authentication")

    profiles = list_profiles()

    if cfg.oci_profile != "DEFAULT" and cfg.oci_profile in profiles:
        # Pre-set via flag or config
        print_success(f"Using profile: {cfg.oci_profile}")
    elif profiles:
        print_step("Available OCI profiles:")
        items = profiles + ["➕ Add a new profile"]
        idx = prompt_selection(items, "Select profile")
        if idx == len(profiles):
            cfg.oci_profile = _setup_new_profile()
        else:
            cfg.oci_profile = profiles[idx]
    else:
        print_info("No OCI profiles found in ~/.oci/config")
        cfg.oci_profile = _setup_new_profile()

    clients = OCIClients(cfg.oci_profile)

    # Test connectivity
    print_step("Testing API connectivity...")
    region = test_connectivity(clients)
    print_success(f"Connected — region: {region}")

    # Populate config from profile
    cfg.tenancy_ocid = clients.config["tenancy"]
    cfg.region = clients.config.get("region", region)
    log(f"Using profile={cfg.oci_profile}, tenancy={cfg.tenancy_ocid}, region={cfg.region}")

    return clients


# ---------------------------------------------------------------------------
# Compartment selection
# ---------------------------------------------------------------------------

def select_compartment(clients: OCIClients, cfg: ReprovisionConfig) -> None:
    """Select compartment interactively (or use pre-set value from config)."""
    if cfg.compartment_ocid:
        print_success(f"Using compartment from config: {cfg.compartment_ocid}")
        return

    print_step("Listing compartments...")
    try:
        resp = clients.identity.list_compartments(
            cfg.tenancy_ocid,
            compartment_id_in_subtree=True,
            lifecycle_state="ACTIVE",
        )
    except oci.exceptions.ServiceError as exc:
        die(f"Failed to list compartments: {exc.message}")

    compartments = resp.data
    # Include root compartment (tenancy itself)
    root_name = "root (tenancy)"
    items = [root_name] + [f"{c.name} ({c.id})" for c in compartments]
    idx = prompt_selection(items, "Select compartment")
    if idx == 0:
        cfg.compartment_ocid = cfg.tenancy_ocid
    else:
        cfg.compartment_ocid = compartments[idx - 1].id
    print_success(f"Compartment: {cfg.compartment_ocid}")
    log(f"Compartment selected: {cfg.compartment_ocid}")


# ---------------------------------------------------------------------------
# Full auth verification (profile + compartment)
# ---------------------------------------------------------------------------

def verify_oci_config(cfg: ReprovisionConfig) -> OCIClients:
    """Complete OCI auth flow: select profile, test connectivity, select compartment."""
    clients = select_profile(cfg)
    select_compartment(clients, cfg)
    return clients


# ---------------------------------------------------------------------------
# New-profile setup wizard
# ---------------------------------------------------------------------------

def _setup_new_profile() -> str:
    """Guide user through creating a new OCI profile. Returns profile name."""
    print_header("New OCI Profile Setup")
    print_info("Choose a setup method:")
    methods = [
        "oci setup bootstrap  — Browser-based login (recommended)",
        "Interactive           — Paste tenancy OCID, user OCID, key path",
        "Existing credentials  — Point to existing PEM key & config values",
    ]
    idx = prompt_selection(methods, "Setup method")

    profile_name = prompt_input("Profile name (e.g. PROD, DEV)", default="DEFAULT")

    if idx == 0:
        _setup_bootstrap(profile_name)
    elif idx == 1:
        _setup_interactive(profile_name)
    else:
        _setup_existing(profile_name)

    return profile_name


def _setup_bootstrap(profile: str) -> None:
    """Run ``oci setup bootstrap`` for browser-based auth."""
    print_step("Launching browser-based OCI login...")
    print_info("A browser window will open. Log in and approve the API key.")
    cmd = ["oci", "setup", "bootstrap", "--profile-name", profile]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        die("oci setup bootstrap failed. Try interactive setup instead.")
    print_success(f"Profile '{profile}' created via bootstrap.")


def _setup_interactive(profile: str) -> None:
    """Step-by-step manual setup — paste tenancy OCID, user OCID, generate key."""
    print_header(f"Interactive Setup — Profile: {profile}")

    print_info("You'll need these values from the OCI Console:")
    print_detail("• Tenancy OCID:  Console → Tenancy Details → OCID")
    print_detail("• User OCID:     Console → Profile → My Profile → OCID")
    print_detail("• Region:        Console → top-right region selector")
    console.print()

    tenancy = prompt_input("Tenancy OCID")
    user = prompt_input("User OCID")
    region = prompt_input("Region identifier (e.g. us-ashburn-1)")

    # Generate API key
    key_dir = Path.home() / ".oci" / "keys" / profile
    key_dir.mkdir(parents=True, exist_ok=True)
    key_path = key_dir / f"{profile}_api_key.pem"
    pub_path = key_dir / f"{profile}_api_key_public.pem"

    if not key_path.exists():
        print_step("Generating API signing key pair...")
        subprocess.run(
            ["openssl", "genrsa", "-out", str(key_path), "2048"],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["openssl", "rsa", "-pubout", "-in", str(key_path), "-out", str(pub_path)],
            capture_output=True,
            check=True,
        )
        os.chmod(key_path, 0o600)
        print_success(f"Key pair saved to {key_dir}/")
    else:
        print_info(f"Key already exists: {key_path}")

    # Compute fingerprint
    fp_result = subprocess.run(
        ["openssl", "rsa", "-pubout", "-outform", "DER", "-in", str(key_path)],
        capture_output=True,
    )
    import hashlib
    fp_hash = hashlib.md5(fp_result.stdout).hexdigest()
    fingerprint = ":".join(fp_hash[i : i + 2] for i in range(0, len(fp_hash), 2))

    # Write to config
    _append_profile(profile, {
        "user": user,
        "tenancy": tenancy,
        "region": region,
        "key_file": str(key_path),
        "fingerprint": fingerprint,
    })

    console.print()
    print_warning("Upload the PUBLIC key to OCI Console:")
    print_detail(f"  cat {pub_path}")
    print_detail("  Console → Profile → API Keys → Add Public Key → Paste")
    prompt_input("Press Enter after uploading the public key…")
    print_success(f"Profile '{profile}' configured.")


def _setup_existing(profile: str) -> None:
    """Use existing PEM key and paste config values."""
    print_header(f"Existing Credentials — Profile: {profile}")
    tenancy = prompt_input("Tenancy OCID")
    user = prompt_input("User OCID")
    region = prompt_input("Region identifier")
    key_file = prompt_input("Path to PEM private key")
    fingerprint = prompt_input("Key fingerprint (xx:xx:…)")

    _append_profile(profile, {
        "user": user,
        "tenancy": tenancy,
        "region": region,
        "key_file": key_file,
        "fingerprint": fingerprint,
    })
    print_success(f"Profile '{profile}' added.")


def _append_profile(name: str, values: dict[str, str]) -> None:
    """Append a profile section to ~/.oci/config."""
    OCI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OCI_CONFIG_PATH, "a") as f:
        f.write(f"\n[{name}]\n")
        for k, v in values.items():
            f.write(f"{k}={v}\n")
