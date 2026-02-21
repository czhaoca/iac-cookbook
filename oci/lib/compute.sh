#!/usr/bin/env bash
# ============================================================================
# oci/lib/compute.sh — Instance & Image Operations
# ============================================================================
# Provides: instance listing/selection, image listing/selection, state mgmt
# Requires: common.sh, auth.sh
# Reads: COMPARTMENT_OCID, OCI_PROFILE
# Sets: INSTANCE_OCID, INSTANCE_NAME, ARCH, AVAILABILITY_DOMAIN,
#       CURRENT_BOOT_VOLUME_ID, CURRENT_BOOT_ATTACH_ID, BOOT_VOLUME_SIZE_GB,
#       IMAGE_OCID
# ============================================================================

[[ -n "${_LIB_COMPUTE_LOADED:-}" ]] && return 0
_LIB_COMPUTE_LOADED=1

# --- State (set by this module) ---
INSTANCE_NAME="${INSTANCE_NAME:-}"
ARCH="${ARCH:-}"
AVAILABILITY_DOMAIN="${AVAILABILITY_DOMAIN:-}"
CURRENT_BOOT_VOLUME_ID="${CURRENT_BOOT_VOLUME_ID:-}"
CURRENT_BOOT_ATTACH_ID="${CURRENT_BOOT_ATTACH_ID:-}"
BOOT_VOLUME_SIZE_GB="${BOOT_VOLUME_SIZE_GB:-}"

# ============================================================================
# Instance Selection
# ============================================================================

select_instance() {
    print_header "Select Instance"

    if [[ -n "$INSTANCE_OCID" ]]; then
        print_info "Instance OCID provided: $INSTANCE_OCID"
    else
        print_info "Listing compute instances in your compartment..."
        print_info "The script will show all instances — you choose which one to work with."
        echo ""

        local instances
        instances=$(oci_cmd compute instance list \
            --compartment-id "$COMPARTMENT_OCID" \
            --all 2>/dev/null)

        local inst_names=()
        local inst_ids=()
        local inst_details=()

        while IFS= read -r line; do
            local name id state shape
            name=$(echo "$line" | jq -r '.["display-name"]')
            id=$(echo "$line" | jq -r '.id')
            state=$(echo "$line" | jq -r '.["lifecycle-state"]')
            shape=$(echo "$line" | jq -r '.shape')
            inst_names+=("$name")
            inst_ids+=("$id")
            inst_details+=("${name}  |  State: ${state}  |  Shape: ${shape}")
        done < <(echo "$instances" | jq -c '.data[] | select(.["lifecycle-state"] != "TERMINATED")')

        if [[ ${#inst_names[@]} -eq 0 ]]; then
            die "No active instances found in compartment $COMPARTMENT_OCID"
        fi

        local idx
        idx=$(prompt_selection "Choose an instance:" "${inst_details[@]}")
        INSTANCE_OCID="${inst_ids[$idx]}"
        print_success "Selected: ${inst_names[$idx]}"
        log_quiet "Instance selected: ${inst_names[$idx]} ($INSTANCE_OCID)"
    fi

    _fetch_instance_details
}

_fetch_instance_details() {
    print_step "Fetching instance details..."
    local instance_data
    instance_data=$(oci_cmd compute instance get --instance-id "$INSTANCE_OCID" 2>/dev/null)

    INSTANCE_NAME=$(echo "$instance_data" | jq -r '.data["display-name"]')
    local shape lifecycle_state
    shape=$(echo "$instance_data" | jq -r '.data.shape')
    lifecycle_state=$(echo "$instance_data" | jq -r '.data["lifecycle-state"]')

    if [[ -z "$AVAILABILITY_DOMAIN" ]]; then
        AVAILABILITY_DOMAIN=$(echo "$instance_data" | jq -r '.data["availability-domain"]')
    fi

    print_detail "Name:        $INSTANCE_NAME"
    print_detail "Shape:       $shape"
    print_detail "State:       $lifecycle_state"
    print_detail "AD:          $AVAILABILITY_DOMAIN"
    print_detail "OCID:        $INSTANCE_OCID"

    # Detect architecture from shape
    if [[ -z "$ARCH" ]]; then
        if echo "$shape" | grep -qiE 'A1|Ampere'; then
            ARCH="arm"
        else
            ARCH="x86"
        fi
    fi
    print_detail "Architecture: $ARCH (detected from shape)"
    log_quiet "Instance: $INSTANCE_NAME, Shape: $shape, State: $lifecycle_state, Arch: $ARCH"

    # Get current boot volume
    print_step "Fetching current boot volume..."
    local boot_volumes
    boot_volumes=$(oci_cmd compute boot-volume-attachment list \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --compartment-id "$COMPARTMENT_OCID" \
        --instance-id "$INSTANCE_OCID" 2>/dev/null)

    # Prefer ATTACHED, fall back to most recent DETACHED (recovery case)
    local attached_bv
    attached_bv=$(echo "$boot_volumes" | jq -r '[.data[] | select(.["lifecycle-state"] == "ATTACHED")] | .[0]')
    if [[ "$attached_bv" != "null" && -n "$attached_bv" ]]; then
        CURRENT_BOOT_VOLUME_ID=$(echo "$attached_bv" | jq -r '.["boot-volume-id"]')
        CURRENT_BOOT_ATTACH_ID=$(echo "$attached_bv" | jq -r '.id')
    else
        local detached_bv
        detached_bv=$(echo "$boot_volumes" | jq -r '[.data[] | select(.["lifecycle-state"] == "DETACHED")] | sort_by(.["time-created"]) | last')
        CURRENT_BOOT_VOLUME_ID=$(echo "$detached_bv" | jq -r '.["boot-volume-id"]')
        CURRENT_BOOT_ATTACH_ID=$(echo "$detached_bv" | jq -r '.id')
        print_warning "Boot volume is currently DETACHED (previous run may have failed)"
    fi
    print_detail "Boot Volume: $CURRENT_BOOT_VOLUME_ID"
    log_quiet "Current boot volume: $CURRENT_BOOT_VOLUME_ID"
    log_quiet "Boot volume attachment: $CURRENT_BOOT_ATTACH_ID"

    # Get boot volume size
    if [[ -z "$BOOT_VOLUME_SIZE_GB" ]]; then
        local bv_data
        bv_data=$(oci_cmd bv boot-volume get --boot-volume-id "$CURRENT_BOOT_VOLUME_ID" 2>/dev/null)
        BOOT_VOLUME_SIZE_GB=$(echo "$bv_data" | jq -r '.data["size-in-gbs"]')
        print_detail "Boot Vol Size: ${BOOT_VOLUME_SIZE_GB} GB"
    fi

    # Save instance metadata for backup
    mkdir -p "$DEFAULT_LOG_DIR"
    echo "$instance_data" | jq '.data' > "$DEFAULT_LOG_DIR/instance-metadata-${TIMESTAMP}.json"
    print_success "Instance metadata backed up to logs"
}

# ============================================================================
# Image Selection
# ============================================================================

select_image() {
    print_header "Select Ubuntu Image"

    if [[ -n "$IMAGE_OCID" ]]; then
        print_info "Image OCID provided: $IMAGE_OCID"
        return
    fi

    print_info "Querying available Ubuntu images for your architecture ($ARCH)..."
    print_info "This searches for official Canonical Ubuntu images in OCI."
    echo ""

    local shape_filter
    if [[ "$ARCH" == "arm" ]]; then
        shape_filter="aarch64"
    else
        shape_filter="x86_64"
    fi

    local images
    images=$(oci_cmd compute image list \
        --compartment-id "$COMPARTMENT_OCID" \
        --operating-system "Canonical Ubuntu" \
        --sort-by TIMECREATED \
        --sort-order DESC \
        --all 2>/dev/null)

    local img_names=()
    local img_ids=()
    local count=0

    while IFS= read -r line; do
        local name id
        name=$(echo "$line" | jq -r '.["display-name"]')
        id=$(echo "$line" | jq -r '.id')
        if echo "$name" | grep -qi "$shape_filter"; then
            img_names+=("$name")
            img_ids+=("$id")
            count=$((count + 1))
            [[ $count -ge 10 ]] && break
        fi
    done < <(echo "$images" | jq -c '.data[]')

    if [[ ${#img_names[@]} -eq 0 ]]; then
        die "No Ubuntu images found for architecture: $ARCH"
    fi

    print_info "Found ${#img_names[@]} Ubuntu images (most recent first):"

    local idx
    idx=$(prompt_selection "Choose an Ubuntu image:" "${img_names[@]}")
    IMAGE_OCID="${img_ids[$idx]}"
    print_success "Selected: ${img_names[$idx]}"
    log_quiet "Image selected: ${img_names[$idx]} ($IMAGE_OCID)"
}

# ============================================================================
# Instance State Management
# ============================================================================

get_instance_state() {
    oci_cmd compute instance get \
        --instance-id "$INSTANCE_OCID" 2>/dev/null \
        | jq -r '.data["lifecycle-state"]'
}

stop_instance() {
    local current_state
    current_state=$(get_instance_state)

    if [[ "$current_state" == "RUNNING" ]]; then
        print_step "Stopping instance..."
        oci_cmd compute instance action \
            --instance-id "$INSTANCE_OCID" \
            --action SOFTSTOP 2>/dev/null >/dev/null
        log "Stop command sent"
        wait_for_state "instance" "$INSTANCE_OCID" "STOPPED"
    else
        print_step "Instance already $current_state — skip stop"
    fi
}

start_instance() {
    local current_state
    current_state=$(get_instance_state)

    if [[ "$current_state" != "RUNNING" ]]; then
        print_step "Starting instance..."
        oci_cmd compute instance action \
            --instance-id "$INSTANCE_OCID" \
            --action START 2>/dev/null >/dev/null || true
        log "Start command sent"
        wait_for_state "instance" "$INSTANCE_OCID" "RUNNING"
    else
        print_step "Instance already running"
    fi
}

wait_for_state() {
    local resource_type="$1"
    local resource_id="$2"
    local target_state="$3"
    local max_wait="${4:-600}"
    local interval=15
    local elapsed=0

    print_info "Waiting for $resource_type to reach state: $target_state ..."

    while (( elapsed < max_wait )); do
        local current_state
        case "$resource_type" in
            instance)
                current_state=$(oci_cmd compute instance get \
                    --instance-id "$resource_id" 2>/dev/null \
                    | jq -r '.data["lifecycle-state"]')
                ;;
            boot-volume)
                current_state=$(oci_cmd bv boot-volume get \
                    --boot-volume-id "$resource_id" 2>/dev/null \
                    | jq -r '.data["lifecycle-state"]')
                ;;
            boot-volume-attachment)
                current_state=$(oci_cmd compute boot-volume-attachment get \
                    --boot-volume-attachment-id "$resource_id" 2>/dev/null \
                    | jq -r '.data["lifecycle-state"]')
                ;;
            boot-volume-backup)
                current_state=$(oci_cmd bv boot-volume-backup get \
                    --boot-volume-backup-id "$resource_id" 2>/dev/null \
                    | jq -r '.data["lifecycle-state"]')
                ;;
        esac

        if [[ "$current_state" == "$target_state" ]]; then
            print_success "$resource_type reached state: $target_state (${elapsed}s)"
            return 0
        fi

        printf "\r    State: %-20s Elapsed: %ds / %ds" "$current_state" "$elapsed" "$max_wait"
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    echo ""
    die "Timeout waiting for $resource_type to reach $target_state after ${max_wait}s"
}
