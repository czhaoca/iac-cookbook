#!/usr/bin/env bash
# ============================================================================
# oci/lib/auth.sh — OCI Authentication & Profile Management
# ============================================================================
# Provides: profile selection, creation, connectivity testing
# Requires: common.sh
# Reads: OCI_CONFIG_FILE, OCI_CONFIG_DIR
# Sets: OCI_PROFILE, TENANCY_OCID, COMPARTMENT_OCID, REGION
# ============================================================================

[[ -n "${_LIB_AUTH_LOADED:-}" ]] && return 0
_LIB_AUTH_LOADED=1

# --- Defaults ---
OCI_CONFIG_DIR="${OCI_CONFIG_DIR:-$HOME/.oci}"
OCI_CONFIG_FILE="${OCI_CONFIG_FILE:-$HOME/.oci/config}"
OCI_PROFILE="${OCI_PROFILE:-DEFAULT}"
COMPARTMENT_OCID="${COMPARTMENT_OCID:-}"

# ============================================================================
# OCI CLI wrapper — all calls use the selected profile
# ============================================================================

oci_cmd() {
    oci --profile "$OCI_PROFILE" "$@"
}

# Run OCI command with error capture and categorized error messages
oci_cmd_checked() {
    local output
    local err_file
    err_file=$(mktemp)
    if output=$(oci --profile "$OCI_PROFILE" "$@" 2>"$err_file"); then
        rm -f "$err_file"
        echo "$output"
        return 0
    else
        local rc=$?
        local err_msg
        err_msg=$(cat "$err_file")
        rm -f "$err_file"
        echo "" >&2
        print_error "OCI CLI command failed:"
        print_detail "  Command: oci --profile $OCI_PROFILE $*"
        if echo "$err_msg" | grep -qi "LimitExceeded\|QuotaExceeded\|Out of host capacity\|TotalStorageExceeded"; then
            print_error "QUOTA EXCEEDED — You've hit a free tier limit."
            print_detail "$err_msg" | head -5
        elif echo "$err_msg" | grep -qi "NotAuthorized\|NotAuthenticated"; then
            print_error "AUTHENTICATION ERROR"
            print_detail "$err_msg" | head -3
        else
            print_detail "$err_msg" | head -5
        fi
        log "OCI CLI error (rc=$rc): $err_msg"
        return $rc
    fi
}

# ============================================================================
# Profile Management
# ============================================================================

# Parse all profile names from ~/.oci/config
list_oci_profiles() {
    if [[ ! -f "$OCI_CONFIG_FILE" ]]; then
        return
    fi
    grep -E '^\[' "$OCI_CONFIG_FILE" | sed 's/\[//;s/\]//' | sort
}

# Get a config value for a specific profile from ~/.oci/config
get_profile_value() {
    local profile="$1" key="$2"
    if [[ ! -f "$OCI_CONFIG_FILE" ]]; then
        return
    fi
    awk -v profile="[$profile]" -v key="$key" '
        $0 == profile { found=1; next }
        /^\[/ { found=0 }
        found && $0 ~ "^"key"[[:space:]]*=" {
            sub(/^[^=]*=[[:space:]]*/, ""); print; exit
        }
    ' "$OCI_CONFIG_FILE"
}

# Test if a profile can connect to OCI
test_profile_connectivity() {
    local profile="$1"
    oci --profile "$profile" iam region list --output json 2>/dev/null | jq -r '.data[0].name' 2>/dev/null
}

# Append a new profile section to ~/.oci/config
append_profile_to_config() {
    local profile="$1" user="$2" fingerprint="$3" tenancy="$4" region="$5" key_file="$6"

    mkdir -p "$OCI_CONFIG_DIR"
    touch "$OCI_CONFIG_FILE"
    chmod 600 "$OCI_CONFIG_FILE"

    if [[ -s "$OCI_CONFIG_FILE" ]]; then
        echo "" >> "$OCI_CONFIG_FILE"
    fi

    cat >> "$OCI_CONFIG_FILE" <<EOF
[${profile}]
user=${user}
fingerprint=${fingerprint}
tenancy=${tenancy}
region=${region}
key_file=${key_file}
EOF
    log_quiet "Profile [$profile] added to $OCI_CONFIG_FILE"
}

# ============================================================================
# Profile Selection (Interactive)
# ============================================================================

select_profile() {
    print_header "OCI Profile Selection"

    print_info "OCI CLI supports multiple profiles in ~/.oci/config."
    print_info "Each profile can connect to a different tenancy, region, or user."
    print_info "Config location: ${CYAN}${OCI_CONFIG_FILE}${NC}"
    echo ""

    if [[ ! -f "$OCI_CONFIG_FILE" ]]; then
        print_warning "No OCI config found at: $OCI_CONFIG_FILE"
        print_info "Let's set up your first OCI profile."
        echo ""
        setup_new_profile "DEFAULT"
        OCI_PROFILE="DEFAULT"
        return
    fi

    local profiles=()
    while IFS= read -r p; do
        profiles+=("$p")
    done < <(list_oci_profiles)

    if [[ ${#profiles[@]} -eq 0 ]]; then
        print_warning "Config file exists but contains no profiles."
        print_info "Let's set up your first OCI profile."
        echo ""
        setup_new_profile "DEFAULT"
        OCI_PROFILE="DEFAULT"
        return
    fi

    # If --profile was provided via CLI, validate and use it
    if [[ "$OCI_PROFILE" != "DEFAULT" ]]; then
        local found=false
        for p in "${profiles[@]}"; do
            if [[ "$p" == "$OCI_PROFILE" ]]; then
                found=true
                break
            fi
        done
        if $found; then
            print_success "Using profile from CLI flag: $OCI_PROFILE"
            return
        else
            print_warning "Profile '$OCI_PROFILE' not found in config."
            print_info "Available profiles: ${profiles[*]}"
            echo ""
        fi
    fi

    # Build selection list with profile details
    local profile_labels=()
    for p in "${profiles[@]}"; do
        local region tenancy_ocid label
        region=$(get_profile_value "$p" "region")
        tenancy_ocid=$(get_profile_value "$p" "tenancy")
        local tenancy_short=""
        if [[ -n "$tenancy_ocid" ]]; then
            tenancy_short="...${tenancy_ocid: -12}"
        fi
        label="[$p]"
        [[ -n "$region" ]] && label="$label  region: $region"
        [[ -n "$tenancy_short" ]] && label="$label  tenancy: $tenancy_short"
        profile_labels+=("$label")
    done
    profile_labels+=("➕ Add a new profile")

    print_info "Found ${#profiles[@]} profile(s) in ~/.oci/config:"
    echo ""

    local idx
    idx=$(prompt_selection "Choose an OCI profile to use:" "${profile_labels[@]}")

    if [[ $idx -lt ${#profiles[@]} ]]; then
        OCI_PROFILE="${profiles[$idx]}"
        print_success "Selected profile: $OCI_PROFILE"
    else
        echo ""
        print_info "Let's set up a new OCI profile."
        echo ""

        local default_name="PROFILE_$(( ${#profiles[@]} + 1 ))"
        print_info "Profile names are typically uppercase: DEFAULT, PROD, DEV, etc."
        local profile_name
        profile_name=$(prompt_input "Profile name" "$default_name")
        profile_name=$(echo "$profile_name" | tr '[:lower:]' '[:upper:]' | tr ' -' '_')

        for p in "${profiles[@]}"; do
            if [[ "$p" == "$profile_name" ]]; then
                print_warning "Profile '$profile_name' already exists. Choose a different name."
                profile_name=$(prompt_input "Profile name")
                profile_name=$(echo "$profile_name" | tr '[:lower:]' '[:upper:]' | tr ' -' '_')
                break
            fi
        done

        setup_new_profile "$profile_name"
        OCI_PROFILE="$profile_name"
    fi

    log_quiet "OCI profile selected: $OCI_PROFILE"
}

# ============================================================================
# Profile Setup Methods
# ============================================================================

setup_new_profile() {
    local profile_name="$1"
    print_step "Setting up profile: [$profile_name]"
    echo ""

    print_info "Choose how you'd like to authenticate with OCI:"
    echo ""

    local method
    method=$(prompt_selection "Choose an authentication method:" \
        "Browser login (easiest — opens browser, auto-configures)" \
        "Interactive CLI setup (step-by-step — paste OCIDs, generate key)" \
        "Use existing credentials (already have OCIDs and key file)")

    echo ""
    case "$method" in
        0) _setup_profile_bootstrap "$profile_name" ;;
        1) _setup_profile_interactive "$profile_name" ;;
        2) _setup_profile_existing "$profile_name" ;;
    esac
}

_setup_profile_bootstrap() {
    local profile_name="$1"
    print_step "Browser-Based Setup (oci setup bootstrap)"
    echo ""
    print_info "This will open a browser window for you to log into OCI."
    print_info "The CLI will automatically:"
    print_detail "• Generate an API signing key pair"
    print_detail "• Upload the public key to your OCI account"
    print_detail "• Create the config profile"
    echo ""
    print_info "Requirements:"
    print_detail "• A web browser accessible from this machine"
    print_detail "• Port 8181 must be available (used for the auth callback)"
    echo ""

    if ! confirm "Ready to open the browser login?"; then
        die "Setup cancelled."
    fi

    mkdir -p "$OCI_CONFIG_DIR"

    if oci setup bootstrap --config-location "$OCI_CONFIG_FILE" --profile-name "$profile_name" 2>/dev/null; then
        print_success "OCI bootstrap complete! Profile [$profile_name] saved."
        log_quiet "Profile [$profile_name] created via bootstrap"
    else
        print_warning "Browser bootstrap didn't work. Falling back to interactive setup."
        _setup_profile_interactive "$profile_name"
    fi
}

_setup_profile_interactive() {
    local profile_name="$1"
    print_step "Interactive CLI Setup for profile [$profile_name]"
    echo ""
    print_info "You'll need to provide your OCIDs — here's where to find them:"
    echo ""
    echo -e "${BOLD}  ┌─────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BOLD}  │  HOW TO FIND YOUR OCI IDENTIFIERS                              │${NC}"
    echo -e "${BOLD}  ├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  ${CYAN}User OCID:${NC}                                                    ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    1. Log in to ${YELLOW}https://cloud.oracle.com${NC}                        ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    2. Click your ${CYAN}Profile icon${NC} (top-right corner)                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    3. Click ${CYAN}\"User Settings\"${NC}                                      ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    4. Under your username, click ${CYAN}\"Copy\"${NC} next to OCID             ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    → Looks like: ${YELLOW}ocid1.user.oc1..aaaaaa...${NC}                      ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  ${CYAN}Tenancy OCID:${NC}                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    1. Click your ${CYAN}Profile icon${NC} (top-right corner)                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    2. Click ${CYAN}\"Tenancy: <your-tenancy-name>\"${NC}                       ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    3. Click ${CYAN}\"Copy\"${NC} next to OCID                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    → Looks like: ${YELLOW}ocid1.tenancy.oc1..aaaaaa...${NC}                   ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  ${CYAN}Region:${NC}                                                       ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    Shown in the top bar of OCI Console                          ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}    → Examples: ${YELLOW}us-ashburn-1${NC}, ${YELLOW}us-phoenix-1${NC}, ${YELLOW}eu-frankfurt-1${NC}      ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  └─────────────────────────────────────────────────────────────────┘${NC}"
    echo ""

    if ! confirm "Do you have your User OCID and Tenancy OCID ready?"; then
        print_info "Take your time. Here's what to do:"
        print_detail "1. Open ${YELLOW}https://cloud.oracle.com${NC} in a browser"
        print_detail "2. Sign in with your OCI account"
        print_detail "3. Follow the steps in the box above to copy your OCIDs"
        echo ""
        read -r -p "$(echo -e "${BOLD}  Press Enter when you're ready to continue...${NC}")"
    fi

    local profile_key_dir="$OCI_CONFIG_DIR/keys/${profile_name}"
    mkdir -p "$profile_key_dir"

    echo ""
    print_step "Let's configure your OCI access step by step."
    echo ""

    # Tenancy OCID
    print_info "${CYAN}Step 1 of 4: Tenancy OCID${NC}"
    print_detail "This identifies your OCI account/organization."
    print_detail "Find it: Profile icon → Tenancy → Copy OCID"
    local tenancy_ocid
    tenancy_ocid=$(prompt_input "Paste your Tenancy OCID")
    while [[ ! "$tenancy_ocid" =~ ^ocid1\.tenancy\. ]]; do
        print_warning "That doesn't look like a tenancy OCID (should start with 'ocid1.tenancy.')"
        tenancy_ocid=$(prompt_input "Paste your Tenancy OCID")
    done
    print_success "Tenancy OCID saved"
    echo ""

    # User OCID
    print_info "${CYAN}Step 2 of 4: User OCID${NC}"
    print_detail "This identifies your OCI user account."
    print_detail "Find it: Profile icon → User Settings → OCID → Copy"
    local user_ocid
    user_ocid=$(prompt_input "Paste your User OCID")
    while [[ ! "$user_ocid" =~ ^ocid1\.user\. ]]; do
        print_warning "That doesn't look like a user OCID (should start with 'ocid1.user.')"
        user_ocid=$(prompt_input "Paste your User OCID")
    done
    print_success "User OCID saved"
    echo ""

    # Region
    print_info "${CYAN}Step 3 of 4: Region${NC}"
    print_detail "Your home region — shown in the OCI Console top bar."
    print_detail "Common regions: us-ashburn-1, us-phoenix-1, us-sanjose-1,"
    print_detail "                eu-frankfurt-1, ap-tokyo-1, uk-london-1, ca-toronto-1"
    local region
    region=$(prompt_input "Enter your region" "us-ashburn-1")
    print_success "Region: $region"
    echo ""

    # API Key
    print_info "${CYAN}Step 4 of 4: API Signing Key${NC}"
    print_detail "OCI uses RSA key pairs for API authentication."
    print_detail "We need a private key on this machine and the matching"
    print_detail "public key uploaded to your OCI user profile."
    print_detail ""
    print_detail "Keys are stored in: ~/.oci/keys/${profile_name}/"
    echo ""

    local default_key_name="oci_api_$(date +%Y%m%d)"

    if ls "$profile_key_dir"/*.pem 2>/dev/null | grep -v '_public' | head -1 >/dev/null 2>&1; then
        print_info "Existing API key(s) found in $profile_key_dir:"
        ls "$profile_key_dir"/*.pem 2>/dev/null | grep -v '_public' | while read -r f; do print_detail "  $f"; done
        echo ""
    fi

    local key_action
    key_action=$(prompt_selection "How would you like to set up the API key?" \
        "Generate a new key (Recommended)" \
        "I already have a key — let me provide the path")

    local key_path pub_path fingerprint=""

    case "$key_action" in
        0)
            local key_name
            key_name=$(prompt_input "Key name" "$default_key_name")
            key_path="${profile_key_dir}/${key_name}.pem"
            pub_path="${profile_key_dir}/${key_name}_public.pem"

            if [[ -f "$key_path" ]]; then
                print_warning "Key already exists at: $key_path"
                if ! confirm "Overwrite it?"; then
                    print_info "Using existing key."
                else
                    openssl genrsa -out "$key_path" 2048 2>/dev/null
                    chmod 600 "$key_path"
                    openssl rsa -pubout -in "$key_path" -out "$pub_path" 2>/dev/null
                    print_success "New key generated at: $key_path"
                fi
            else
                openssl genrsa -out "$key_path" 2048 2>/dev/null
                chmod 600 "$key_path"
                openssl rsa -pubout -in "$key_path" -out "$pub_path" 2>/dev/null
                print_success "Key generated at: $key_path"
            fi

            fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')
            ;;
        1)
            key_path=$(prompt_input "Path to your private key (.pem)")
            while [[ ! -f "$key_path" ]]; do
                print_warning "File not found: $key_path"
                key_path=$(prompt_input "Path to your private key (.pem)")
            done
            pub_path="${key_path%.pem}_public.pem"
            if [[ ! -f "$pub_path" ]]; then
                openssl rsa -pubout -in "$key_path" -out "$pub_path" 2>/dev/null
                print_info "Generated public key: $pub_path"
            fi
            local base
            base=$(basename "$key_path")
            cp "$key_path" "$profile_key_dir/$base"
            cp "$pub_path" "$profile_key_dir/$(basename "$pub_path")"
            chmod 600 "$profile_key_dir/$base"
            key_path="$profile_key_dir/$base"
            pub_path="$profile_key_dir/$(basename "$pub_path")"
            fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')
            print_success "Key copied to: $profile_key_dir/"
            ;;
    esac

    print_info "Key fingerprint: $fingerprint"
    echo ""

    # Guide user to upload the public key
    print_step "Now upload the public key to your OCI account"
    echo ""
    echo -e "${BOLD}  ┌─────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${BOLD}  │  UPLOAD YOUR PUBLIC KEY TO OCI                                  │${NC}"
    echo -e "${BOLD}  ├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  1. Go to ${YELLOW}https://cloud.oracle.com${NC}                              ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  2. Click ${CYAN}Profile icon${NC} (top-right) → ${CYAN}\"User Settings\"${NC}           ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  3. Go to ${CYAN}\"Tokens and keys\"${NC} (under Resources, left sidebar)     ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  4. Click ${CYAN}\"Add API Key\"${NC}                                         ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  5. Select ${CYAN}\"Paste a Public Key\"${NC}                                  ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  6. Paste the key shown below                                   ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  7. Click ${CYAN}\"Add\"${NC}                                                  ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  After clicking Add, OCI will show a                             ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  ${GREEN}\"Configuration File Preview\"${NC} — you don't need to copy it,      ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}  we already have all the values.                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  │${NC}                                                                 ${BOLD}│${NC}"
    echo -e "${BOLD}  └─────────────────────────────────────────────────────────────────┘${NC}"
    echo ""
    echo -e "${BOLD}  Your public key to paste:${NC}"
    echo -e "${YELLOW}"
    cat "$pub_path"
    echo -e "${NC}"

    if ! $NON_INTERACTIVE; then
        read -r -p "$(echo -e "${BOLD}  Press Enter after you've uploaded the key to OCI Console...${NC}")" </dev/tty
    fi

    append_profile_to_config "$profile_name" "$user_ocid" "$fingerprint" "$tenancy_ocid" "$region" "$key_path"
    print_success "Profile [$profile_name] saved to: $OCI_CONFIG_FILE"
}

_setup_profile_existing() {
    local profile_name="$1"
    print_step "Use Existing Credentials for profile [$profile_name]"
    echo ""

    print_info "You'll need: User OCID, Tenancy OCID, Region, and key file path."
    echo ""

    local user_ocid tenancy_ocid region key_path fingerprint

    tenancy_ocid=$(prompt_input "Tenancy OCID")
    while [[ ! "$tenancy_ocid" =~ ^ocid1\.tenancy\. ]]; do
        print_warning "Should start with 'ocid1.tenancy.'"
        tenancy_ocid=$(prompt_input "Tenancy OCID")
    done

    user_ocid=$(prompt_input "User OCID")
    while [[ ! "$user_ocid" =~ ^ocid1\.user\. ]]; do
        print_warning "Should start with 'ocid1.user.'"
        user_ocid=$(prompt_input "User OCID")
    done

    region=$(prompt_input "Region" "us-ashburn-1")

    key_path=$(prompt_input "Path to private key (.pem)")
    while [[ ! -f "$key_path" ]]; do
        print_warning "File not found: $key_path"
        key_path=$(prompt_input "Path to private key (.pem)")
    done

    local profile_key_dir="$OCI_CONFIG_DIR/keys/${profile_name}"
    mkdir -p "$profile_key_dir"
    local base
    base=$(basename "$key_path")
    cp "$key_path" "$profile_key_dir/$base"
    chmod 600 "$profile_key_dir/$base"
    key_path="$profile_key_dir/$base"

    fingerprint=$(openssl rsa -pubout -outform DER -in "$key_path" 2>/dev/null | openssl md5 -c | awk '{print $2}')

    append_profile_to_config "$profile_name" "$user_ocid" "$fingerprint" "$tenancy_ocid" "$region" "$key_path"
    print_success "Profile [$profile_name] saved to: $OCI_CONFIG_FILE"
}

# ============================================================================
# Verify OCI Config & Select Compartment
# ============================================================================

verify_oci_config() {
    select_profile

    echo ""
    print_step "Testing OCI API connectivity for profile [$OCI_PROFILE]..."
    if test_profile_connectivity "$OCI_PROFILE"; then
        print_success "OCI API connection successful!"
        log_quiet "OCI API connection verified (profile: $OCI_PROFILE)"
    else
        print_warning "First attempt failed. Waiting 5 seconds for key propagation..."
        sleep 5
        if test_profile_connectivity "$OCI_PROFILE"; then
            print_success "OCI API connection successful (after retry)!"
            log_quiet "OCI API connection verified (profile: $OCI_PROFILE, retry)"
        else
            print_error "Connection failed. Common issues:"
            print_detail "• API key not uploaded to OCI Console yet"
            print_detail "• Fingerprint mismatch (re-generate and re-upload key)"
            print_detail "• User/Tenancy OCID typo (verify in OCI Console)"
            print_detail "• Region incorrect (check OCI Console top bar)"
            echo ""
            print_info "Your config file: $OCI_CONFIG_FILE"
            print_info "Edit profile [$OCI_PROFILE] with: nano $OCI_CONFIG_FILE"
            die "OCI API connection failed. Fix the config and re-run."
        fi
    fi

    TENANCY_OCID=$(get_profile_value "$OCI_PROFILE" "tenancy")
    REGION=$(get_profile_value "$OCI_PROFILE" "region")

    if [[ -z "$TENANCY_OCID" ]]; then
        die "Could not read tenancy OCID from profile [$OCI_PROFILE] in $OCI_CONFIG_FILE"
    fi

    # Get or prompt for compartment OCID
    if [[ -z "$COMPARTMENT_OCID" ]]; then
        echo ""
        print_step "Select a compartment"
        print_info "A compartment is an OCI container for organizing your cloud resources."
        print_info "Most users have a 'root' compartment (the tenancy itself) and may"
        print_info "have additional compartments for different projects or environments."
        print_info "Listing compartments in your tenancy..."
        echo ""

        local compartments
        compartments=$(oci_cmd iam compartment list \
            --compartment-id "$TENANCY_OCID" \
            --compartment-id-in-subtree true \
            --lifecycle-state ACTIVE \
            --all 2>/dev/null)

        local comp_names=()
        local comp_ids=()

        comp_names+=("Root compartment (tenancy) — use if unsure")
        comp_ids+=("$TENANCY_OCID")

        while IFS= read -r line; do
            local name id desc
            name=$(echo "$line" | jq -r '.name')
            id=$(echo "$line" | jq -r '.id')
            desc=$(echo "$line" | jq -r '.description // ""' | head -c 50)
            if [[ -n "$desc" ]]; then
                comp_names+=("$name — $desc")
            else
                comp_names+=("$name")
            fi
            comp_ids+=("$id")
        done < <(echo "$compartments" | jq -c '.data[]')

        local idx
        idx=$(prompt_selection "Choose the compartment where your instances live:" "${comp_names[@]}")
        COMPARTMENT_OCID="${comp_ids[$idx]}"
        print_success "Selected: ${comp_names[$idx]}"
        log_quiet "Compartment: ${comp_names[$idx]} ($COMPARTMENT_OCID)"
    fi
}
