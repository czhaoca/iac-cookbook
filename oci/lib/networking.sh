#!/usr/bin/env bash
# ============================================================================
# oci/lib/networking.sh — Network & SSH Connectivity
# ============================================================================
# Provides: VNIC/IP lookup, SSH connectivity verification
# Requires: common.sh, auth.sh
# Reads: COMPARTMENT_OCID, INSTANCE_OCID, OCI_PROFILE
# Sets: PUBLIC_IP, PRIVATE_IP
# ============================================================================

[[ -n "${_LIB_NETWORKING_LOADED:-}" ]] && return 0
_LIB_NETWORKING_LOADED=1

# --- State ---
PUBLIC_IP="${PUBLIC_IP:-}"
PRIVATE_IP="${PRIVATE_IP:-}"

# ============================================================================
# VNIC & IP Lookup
# ============================================================================

fetch_instance_network_info() {
    print_step "Fetching network details..."
    local vnic_attachments
    vnic_attachments=$(oci_cmd compute vnic-attachment list \
        --compartment-id "$COMPARTMENT_OCID" \
        --instance-id "$INSTANCE_OCID" 2>/dev/null)

    local vnic_id
    vnic_id=$(echo "$vnic_attachments" | jq -r '.data[0]["vnic-id"]')
    if [[ -n "$vnic_id" && "$vnic_id" != "null" ]]; then
        local vnic_data
        vnic_data=$(oci_cmd network vnic get --vnic-id "$vnic_id" 2>/dev/null)
        PUBLIC_IP=$(echo "$vnic_data" | jq -r '.data["public-ip"] // "none"')
        PRIVATE_IP=$(echo "$vnic_data" | jq -r '.data["private-ip"] // "none"')
        print_detail "Public IP:   $PUBLIC_IP"
        print_detail "Private IP:  $PRIVATE_IP"
        log_quiet "Public IP: $PUBLIC_IP, Private IP: $PRIVATE_IP, VNIC: $vnic_id"
    else
        print_warning "No VNIC found for instance"
    fi
}

get_public_ip() {
    if [[ -z "$PUBLIC_IP" || "$PUBLIC_IP" == "none" ]]; then
        fetch_instance_network_info
    fi
    echo "$PUBLIC_IP"
}

# ============================================================================
# SSH Connectivity Verification
# ============================================================================

verify_ssh_connectivity() {
    local ssh_user="${1:-$NEW_USERNAME}"
    local ssh_key="${2:-$SSH_PRIVATE_KEY_PATH}"
    local target_ip="${3:-}"

    if [[ -z "$target_ip" ]]; then
        target_ip=$(get_public_ip)
    fi

    if [[ -z "$target_ip" || "$target_ip" == "none" ]]; then
        print_warning "No public IP found. SSH verification skipped."
        return 1
    fi

    print_step "Verifying SSH connectivity..."
    print_info "Waiting 60 seconds for cloud-init to start..."
    sleep 60

    local ssh_key_flag=""
    [[ -n "$ssh_key" && -f "$ssh_key" ]] && ssh_key_flag="-i $ssh_key"

    local retries=5
    local connected=false
    for (( i=1; i<=retries; i++ )); do
        print_info "SSH attempt $i/$retries to ${ssh_user}@${target_ip}..."
        if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            $ssh_key_flag "${ssh_user}@${target_ip}" \
            "echo 'SSH connection successful'" 2>/dev/null; then
            connected=true
            break
        fi
        sleep 15
    done

    if $connected; then
        print_success "SSH connection verified! Instance is ready."
        return 0
    else
        print_warning "SSH connection could not be verified after $retries attempts."
        print_info "The instance may still be running cloud-init. Try manually:"
        print_detail "ssh $ssh_key_flag ${ssh_user}@${target_ip}"
        return 1
    fi
}
