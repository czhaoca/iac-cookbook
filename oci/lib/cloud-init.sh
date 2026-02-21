#!/usr/bin/env bash
# ============================================================================
# oci/lib/cloud-init.sh — SSH Key, User Config & Cloud-Init Template
# ============================================================================
# Provides: SSH key selection/generation, user/password config, cloud-init
#           template selection and variable substitution
# Requires: common.sh
# Reads: DEFAULT_SSH_DIR, INSTALL_CLOUDPANEL
# Sets: SSH_PUBLIC_KEY_PATH, SSH_PRIVATE_KEY_PATH, NEW_USERNAME, NEW_PASSWORD,
#       INSTALL_CLOUDPANEL, CLOUDPANEL_ADMIN_EMAIL, CLOUDPANEL_DB_ENGINE,
#       CLOUD_INIT_PATH, CLOUD_INIT_PREPARED
# ============================================================================

[[ -n "${_LIB_CLOUD_INIT_LOADED:-}" ]] && return 0
_LIB_CLOUD_INIT_LOADED=1

# --- State ---
SSH_PUBLIC_KEY_PATH="${SSH_PUBLIC_KEY_PATH:-}"
SSH_PRIVATE_KEY_PATH="${SSH_PRIVATE_KEY_PATH:-}"
NEW_USERNAME="${NEW_USERNAME:-}"
NEW_PASSWORD="${NEW_PASSWORD:-}"
INSTALL_CLOUDPANEL="${INSTALL_CLOUDPANEL:-false}"
CLOUDPANEL_ADMIN_EMAIL="${CLOUDPANEL_ADMIN_EMAIL:-}"
CLOUDPANEL_DB_ENGINE="${CLOUDPANEL_DB_ENGINE:-MYSQL_8.4}"
CLOUD_INIT_PATH="${CLOUD_INIT_PATH:-}"
CLOUD_INIT_PREPARED="${CLOUD_INIT_PREPARED:-}"

DEFAULT_SSH_DIR="${DEFAULT_SSH_DIR:-$REPO_ROOT/oci/local/ssh}"

# ============================================================================
# SSH Key Selection
# ============================================================================

select_ssh_key() {
    print_header "SSH Key Configuration"

    print_info "The new OS will be configured with SSH key-only authentication."
    print_info "Password login will be DISABLED for security."
    echo ""

    mkdir -p "$DEFAULT_SSH_DIR"

    if [[ -n "$SSH_PUBLIC_KEY_PATH" && -f "$SSH_PUBLIC_KEY_PATH" ]]; then
        print_success "SSH public key: $SSH_PUBLIC_KEY_PATH"
    else
        local pub_keys=()
        if [[ -d "$DEFAULT_SSH_DIR" ]]; then
            while IFS= read -r -d '' keyfile; do
                pub_keys+=("$keyfile")
            done < <(find "$DEFAULT_SSH_DIR" -name "*.pub" -print0 2>/dev/null)
        fi

        local home_keys=()
        if [[ -d "$HOME/.ssh" ]]; then
            while IFS= read -r -d '' keyfile; do
                home_keys+=("$keyfile")
            done < <(find "$HOME/.ssh" -name "*.pub" -print0 2>/dev/null)
        fi

        local all_keys=() all_labels=()
        for k in "${pub_keys[@]}"; do
            all_keys+=("$k")
            all_labels+=("[repo] $k")
        done
        for k in "${home_keys[@]}"; do
            all_keys+=("$k")
            all_labels+=("[home] $k")
        done
        all_labels+=("Generate a new SSH key")

        if [[ ${#pub_keys[@]} -eq 0 && ${#home_keys[@]} -eq 0 ]]; then
            print_warning "No SSH keys found in $DEFAULT_SSH_DIR or ~/.ssh/"
            echo ""
            print_info "Let's generate a new SSH key pair."
        fi

        local idx
        idx=$(prompt_selection "Choose an SSH public key:" "${all_labels[@]}")

        if [[ $idx -eq ${#all_keys[@]} ]]; then
            local default_name="oci_bash_$(date +%Y%m%d)"
            echo "" >/dev/tty
            print_info "The key will be generated in ~/.ssh/"
            print_info "Default name: ${CYAN}${default_name}${NC}"
            print_info "Enter a custom name or press Enter for the default."
            echo "" >/dev/tty

            local key_name
            key_name=$(prompt_input "SSH key name" "$default_name")
            local key_path="$HOME/.ssh/${key_name}"

            if [[ -f "$key_path" ]]; then
                print_warning "Key already exists: $key_path"
                if confirm "Use existing key instead of overwriting?"; then
                    SSH_PUBLIC_KEY_PATH="${key_path}.pub"
                    SSH_PRIVATE_KEY_PATH="$key_path"
                else
                    ssh-keygen -t ed25519 -f "$key_path" -N "" -C "${key_name}" <<< "y"
                    SSH_PUBLIC_KEY_PATH="${key_path}.pub"
                    SSH_PRIVATE_KEY_PATH="$key_path"
                fi
            else
                ssh-keygen -t ed25519 -f "$key_path" -N "" -C "${key_name}"
                SSH_PUBLIC_KEY_PATH="${key_path}.pub"
                SSH_PRIVATE_KEY_PATH="$key_path"
            fi

            print_success "SSH key ready:"
            print_detail "Private: $SSH_PRIVATE_KEY_PATH"
            print_detail "Public:  $SSH_PUBLIC_KEY_PATH"

            mkdir -p "$DEFAULT_SSH_DIR"
            cp "$SSH_PUBLIC_KEY_PATH" "$DEFAULT_SSH_DIR/"
            cp "$SSH_PRIVATE_KEY_PATH" "$DEFAULT_SSH_DIR/"
            chmod 600 "$DEFAULT_SSH_DIR/$(basename "$SSH_PRIVATE_KEY_PATH")"
            print_info "Key also copied to: $DEFAULT_SSH_DIR/ (gitignored)"
        else
            SSH_PUBLIC_KEY_PATH="${all_keys[$idx]}"
            SSH_PRIVATE_KEY_PATH="${SSH_PUBLIC_KEY_PATH%.pub}"

            if [[ "$SSH_PUBLIC_KEY_PATH" == "$HOME/.ssh/"* ]]; then
                if confirm "Copy this key to $DEFAULT_SSH_DIR for this project?"; then
                    mkdir -p "$DEFAULT_SSH_DIR"
                    cp "$SSH_PUBLIC_KEY_PATH" "$DEFAULT_SSH_DIR/"
                    [[ -f "$SSH_PRIVATE_KEY_PATH" ]] && cp "$SSH_PRIVATE_KEY_PATH" "$DEFAULT_SSH_DIR/"
                    local basename
                    basename=$(basename "$SSH_PUBLIC_KEY_PATH")
                    SSH_PUBLIC_KEY_PATH="$DEFAULT_SSH_DIR/$basename"
                    SSH_PRIVATE_KEY_PATH="${SSH_PUBLIC_KEY_PATH%.pub}"
                    print_success "Key copied to: $DEFAULT_SSH_DIR/"
                fi
            fi
        fi
    fi

    log_quiet "SSH public key: $SSH_PUBLIC_KEY_PATH"
    print_detail "Key fingerprint: $(ssh-keygen -lf "$SSH_PUBLIC_KEY_PATH" 2>/dev/null | awk '{print $2}')"
}

# ============================================================================
# User & OS Configuration
# ============================================================================

configure_user() {
    print_header "New User & OS Configuration"

    print_info "The new OS will be hardened with the following security settings:"
    print_detail "• Default 'ubuntu' user will be DISABLED"
    print_detail "• SSH password authentication will be DISABLED"
    print_detail "• Only SSH key login will be allowed"
    print_detail "• A new admin user with sudo access will be created"
    echo ""

    if [[ -z "$NEW_USERNAME" ]]; then
        NEW_USERNAME=$(prompt_input "New admin username" "admin")
    fi
    print_success "Admin username: $NEW_USERNAME"

    if [[ -z "$NEW_PASSWORD" ]]; then
        print_info "Set a password for sudo operations (SSH will use key only)."
        while true; do
            NEW_PASSWORD=$(prompt_password "Password for $NEW_USERNAME")
            local confirm_pw
            confirm_pw=$(prompt_password "Confirm password")
            if [[ "$NEW_PASSWORD" == "$confirm_pw" ]]; then
                break
            fi
            print_warning "Passwords don't match. Try again."
        done
    fi
    print_success "Password configured (will be hashed before use)"

    echo ""
    _configure_cloudpanel

    log_quiet "User config: username=$NEW_USERNAME, cloudpanel=$INSTALL_CLOUDPANEL"
}

_configure_cloudpanel() {
    print_step "CloudPanel Installation"
    print_info "CloudPanel is a free server control panel for PHP, Node.js, Python apps."
    print_info "It provides a web-based admin UI at https://<your-ip>:8443"
    echo ""

    if [[ "$INSTALL_CLOUDPANEL" == "true" ]]; then
        print_success "CloudPanel installation: ENABLED (from config)"
    else
        if confirm "Install CloudPanel on the new instance?"; then
            INSTALL_CLOUDPANEL=true
            print_success "CloudPanel will be installed"
        else
            INSTALL_CLOUDPANEL=false
            print_info "CloudPanel will NOT be installed"
        fi
    fi

    if [[ "$INSTALL_CLOUDPANEL" == "true" && -z "$CLOUDPANEL_ADMIN_EMAIL" ]]; then
        CLOUDPANEL_ADMIN_EMAIL=$(prompt_input "CloudPanel admin email" "admin@example.com")
    fi

    if [[ "$INSTALL_CLOUDPANEL" == "true" ]]; then
        print_info "CloudPanel database engine (per cloudpanel.io docs):"
        local db_idx
        db_idx=$(prompt_selection "Choose database engine:" \
            "MySQL 8.4 (Recommended)" \
            "MySQL 8.0" \
            "MariaDB 11.4" \
            "MariaDB 10.11")
        case "$db_idx" in
            0) CLOUDPANEL_DB_ENGINE="MYSQL_8.4" ;;
            1) CLOUDPANEL_DB_ENGINE="MYSQL_8.0" ;;
            2) CLOUDPANEL_DB_ENGINE="MARIADB_11.4" ;;
            3) CLOUDPANEL_DB_ENGINE="MARIADB_10.11" ;;
        esac
        print_success "Database engine: $CLOUDPANEL_DB_ENGINE"
    fi
}

# ============================================================================
# Instance Config Save
# ============================================================================

save_instance_config() {
    local config_file="$1"

    if ! $NON_INTERACTIVE; then
        if confirm "Save these settings to $config_file for future runs?"; then
            mkdir -p "$(dirname "$config_file")"
            cat > "$config_file" <<EOF
# Instance configuration — generated on $(date)
# This file is gitignored. Do not commit to version control.

COMPARTMENT_OCID=${COMPARTMENT_OCID}
INSTANCE_OCID=${INSTANCE_OCID}
SSH_PUBLIC_KEY_PATH=${SSH_PUBLIC_KEY_PATH}
SSH_PRIVATE_KEY_PATH=${SSH_PRIVATE_KEY_PATH}
NEW_USERNAME=${NEW_USERNAME}
NEW_PASSWORD=${NEW_PASSWORD}
INSTALL_CLOUDPANEL=${INSTALL_CLOUDPANEL}
CLOUDPANEL_ADMIN_EMAIL=${CLOUDPANEL_ADMIN_EMAIL}
CLOUDPANEL_DB_ENGINE=${CLOUDPANEL_DB_ENGINE}
OCI_PROFILE=${OCI_PROFILE}
AVAILABILITY_DOMAIN=${AVAILABILITY_DOMAIN}
BOOT_VOLUME_SIZE_GB=${BOOT_VOLUME_SIZE_GB}
ARCH=${ARCH}
EOF
            chmod 600 "$config_file"
            print_success "Config saved to: $config_file"
        fi
    fi
}

# ============================================================================
# Cloud-Init Template Processing
# ============================================================================

select_cloud_init_template() {
    print_header "Cloud-Init Configuration"

    print_info "Cloud-init runs on first boot to configure the new OS."
    print_info "It will set up your admin user, SSH keys, and security settings."
    echo ""

    if [[ -n "$CLOUD_INIT_PATH" && -f "$CLOUD_INIT_PATH" ]]; then
        print_success "Cloud-init template: $CLOUD_INIT_PATH"
    else
        local templates_dir="$REPO_ROOT/oci/templates/cloud-init"
        local tmpl_files=() tmpl_labels=()

        if [[ -d "$templates_dir" ]]; then
            while IFS= read -r f; do
                tmpl_files+=("$f")
                local basename desc
                basename=$(basename "$f")
                desc=$(head -3 "$f" | grep -oP '(?<=# ).*' | head -1)
                tmpl_labels+=("$basename — $desc")
            done < <(find "$templates_dir" -name "*.yaml" -o -name "*.yml" | sort)
        fi

        if [[ ${#tmpl_files[@]} -eq 0 ]]; then
            print_warning "No cloud-init templates found in $templates_dir"
            CLOUD_INIT_PATH=""
        else
            if [[ "$INSTALL_CLOUDPANEL" == "true" ]]; then
                for i in "${!tmpl_files[@]}"; do
                    if echo "${tmpl_files[$i]}" | grep -qi "cloudpanel"; then
                        CLOUD_INIT_PATH="${tmpl_files[$i]}"
                        print_success "Auto-selected CloudPanel template: $(basename "$CLOUD_INIT_PATH")"
                        break
                    fi
                done
            fi

            if [[ -z "$CLOUD_INIT_PATH" ]]; then
                tmpl_labels+=("No cloud-init (manual setup)")
                local idx
                idx=$(prompt_selection "Choose a cloud-init template:" "${tmpl_labels[@]}")
                if [[ $idx -lt ${#tmpl_files[@]} ]]; then
                    CLOUD_INIT_PATH="${tmpl_files[$idx]}"
                    print_success "Selected: $(basename "$CLOUD_INIT_PATH")"
                else
                    CLOUD_INIT_PATH=""
                    print_info "No cloud-init template selected"
                fi
            fi
        fi
    fi
}

prepare_cloud_init() {
    if [[ -z "${CLOUD_INIT_PATH:-}" ]]; then
        return
    fi

    print_step "Preparing cloud-init with your configuration..."
    local prepared_dir="$REPO_ROOT/oci/local/config"
    mkdir -p "$prepared_dir"
    local prepared_file="$prepared_dir/cloud-init-prepared.yaml"

    local password_hash
    password_hash=$(openssl passwd -6 "$NEW_PASSWORD")

    local ssh_pub_key
    ssh_pub_key=$(cat "$SSH_PUBLIC_KEY_PATH")

    local db_engine="${CLOUDPANEL_DB_ENGINE:-MYSQL_8.4}"
    sed \
        -e "s|__NEW_USERNAME__|${NEW_USERNAME}|g" \
        -e "s|__NEW_PASSWORD_HASH__|${password_hash}|g" \
        -e "s|__SSH_PUBLIC_KEY__|${ssh_pub_key}|g" \
        -e "s|__CLOUDPANEL_DB_ENGINE__|${db_engine}|g" \
        "$CLOUD_INIT_PATH" > "$prepared_file"

    CLOUD_INIT_PREPARED="$prepared_file"
    print_success "Cloud-init prepared: $prepared_file"
    log_quiet "Cloud-init prepared from $CLOUD_INIT_PATH"
}

# ============================================================================
# Build Instance Metadata (SSH key + cloud-init user data)
# ============================================================================

build_instance_metadata() {
    local ssh_pub_key
    ssh_pub_key=$(cat "$SSH_PUBLIC_KEY_PATH")

    if [[ -n "${CLOUD_INIT_PREPARED:-}" && -f "${CLOUD_INIT_PREPARED}" ]]; then
        local user_data_b64
        user_data_b64=$(base64 -w 0 "$CLOUD_INIT_PREPARED")
        jq -n \
            --arg ssh "$ssh_pub_key" \
            --arg ud "$user_data_b64" \
            '{"ssh_authorized_keys": $ssh, "user_data": $ud}'
    else
        jq -n \
            --arg ssh "$ssh_pub_key" \
            '{"ssh_authorized_keys": $ssh}'
    fi
}
