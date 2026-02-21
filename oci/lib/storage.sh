#!/usr/bin/env bash
# ============================================================================
# oci/lib/storage.sh — Boot Volume & Block Volume Operations
# ============================================================================
# Provides: quota checking, boot volume replacement, backup management
# Requires: common.sh, auth.sh, compute.sh
# Reads: OCI_PROFILE, COMPARTMENT_OCID, INSTANCE_OCID, AVAILABILITY_DOMAIN,
#        CURRENT_BOOT_VOLUME_ID, BOOT_VOLUME_SIZE_GB, IMAGE_OCID
# Sets: DELETE_OLD_BV, SKIP_BACKUP, new_bv_id
# ============================================================================

[[ -n "${_LIB_STORAGE_LOADED:-}" ]] && return 0
_LIB_STORAGE_LOADED=1

# --- State ---
SKIP_BACKUP="${SKIP_BACKUP:-false}"
DELETE_OLD_BV="${DELETE_OLD_BV:-false}"
new_bv_id="${new_bv_id:-}"

# ============================================================================
# Storage Quota Check
# ============================================================================

check_storage_quota() {
    print_step "Checking storage quota..."

    local ad
    ad=$(oci_cmd iam availability-domain list 2>/dev/null | jq -r '.data[0].name')

    local storage_limit
    storage_limit=$(oci_cmd limits value list \
        --compartment-id "$(get_profile_value "$OCI_PROFILE" "tenancy")" \
        --service-name block-storage --all 2>/dev/null \
        | jq -r '.data[] | select(.name == "total-free-storage-gb") | .value' | head -1)

    if [[ -z "$storage_limit" || "$storage_limit" == "null" ]]; then
        print_info "Could not determine storage quota. Proceeding anyway."
        return 0
    fi

    local tenancy_ocid
    tenancy_ocid=$(get_profile_value "$OCI_PROFILE" "tenancy")

    local bv_usage=0 bv_list
    bv_list=$(oci_cmd bv boot-volume list \
        --compartment-id "$tenancy_ocid" \
        --availability-domain "$ad" 2>/dev/null || echo '{"data":[]}')
    bv_usage=$(echo "$bv_list" | jq '[.data[] | .["size-in-gbs"] // 0] | add // 0')

    local backup_usage=0 backup_list
    backup_list=$(oci_cmd bv boot-volume-backup list \
        --compartment-id "$tenancy_ocid" 2>/dev/null || echo '{"data":[]}')
    backup_usage=$(echo "$backup_list" | jq '[.data[] | .["size-in-gbs"] // 0] | add // 0')

    local vol_usage=0 vol_list
    vol_list=$(oci_cmd bv volume list \
        --compartment-id "$tenancy_ocid" \
        --availability-domain "$ad" 2>/dev/null || echo '{"data":[]}')
    vol_usage=$(echo "$vol_list" | jq '[.data[] | .["size-in-gbs"] // 0] | add // 0')

    local total_used=$(( bv_usage + backup_usage + vol_usage ))
    local available=$(( storage_limit - total_used ))

    echo ""
    print_info "┌─── Block Storage Quota ─────────────────────────────────┐"
    print_info "│ Free tier limit:     ${storage_limit} GB"
    print_info "│ Boot volumes:        ${bv_usage} GB"
    print_info "│ Boot vol backups:    ${backup_usage} GB"
    print_info "│ Block volumes:       ${vol_usage} GB"
    print_info "│ Total used:          ${total_used} GB"
    print_info "│ Available:           ${available} GB"
    print_info "│ Needed for new BV:   ${BOOT_VOLUME_SIZE_GB} GB"
    print_info "└─────────────────────────────────────────────────────────┘"
    echo ""
    log "Storage quota: limit=${storage_limit}GB, used=${total_used}GB, available=${available}GB, needed=${BOOT_VOLUME_SIZE_GB}GB"

    if (( available >= BOOT_VOLUME_SIZE_GB )); then
        print_success "Sufficient storage available."
        return 0
    fi

    # Not enough space — help the user
    print_warning "NOT ENOUGH STORAGE for a new ${BOOT_VOLUME_SIZE_GB} GB boot volume."
    print_info "You need to free up $(( BOOT_VOLUME_SIZE_GB - available )) GB."
    echo ""

    local strategies=()
    local strategy_actions=()

    strategies+=("Don't preserve old boot volume (OCI replaces in-place — no rollback)")
    strategy_actions+=("delete_old_bv")

    local backup_count
    backup_count=$(echo "$backup_list" | jq '.data | length')
    if (( backup_count > 0 )); then
        strategies+=("Delete existing backup(s) (frees ${backup_usage} GB from ${backup_count} backup(s))")
        strategy_actions+=("delete_backups")
    fi

    strategies+=("Abort — I'll free space manually")
    strategy_actions+=("abort")

    print_info "Choose a strategy to free storage:"
    echo ""

    local freed=0
    while (( available + freed < BOOT_VOLUME_SIZE_GB )); do
        local idx
        idx=$(prompt_selection "Free up storage (still need $(( BOOT_VOLUME_SIZE_GB - available - freed )) GB more):" "${strategies[@]}")
        local action="${strategy_actions[$idx]}"

        case "$action" in
            delete_backups)
                print_info "Existing backups:"
                local backup_names=() backup_ids=() backup_sizes=()
                while IFS= read -r line; do
                    local bname bsize bid
                    bname=$(echo "$line" | jq -r '.["display-name"]')
                    bsize=$(echo "$line" | jq -r '.["size-in-gbs"]')
                    bid=$(echo "$line" | jq -r '.id')
                    backup_names+=("$bname (${bsize} GB)")
                    backup_ids+=("$bid")
                    backup_sizes+=("$bsize")
                done < <(echo "$backup_list" | jq -c '.data[]')

                backup_names+=("Cancel — don't delete any")
                local bidx
                bidx=$(prompt_selection "Which backup to delete?" "${backup_names[@]}")
                if (( bidx < ${#backup_ids[@]} )); then
                    local del_id="${backup_ids[$bidx]}"
                    local del_size="${backup_sizes[$bidx]}"
                    if confirm "Delete backup '${backup_names[$bidx]}'? This cannot be undone."; then
                        print_info "Deleting backup..."
                        oci_cmd bv boot-volume-backup delete \
                            --boot-volume-backup-id "$del_id" --force 2>/dev/null
                        freed=$((freed + del_size))
                        print_success "Deleted. Freed ${del_size} GB."
                        log "Deleted backup $del_id (${del_size} GB)"
                    fi
                fi
                ;;
            delete_old_bv)
                DELETE_OLD_BV=true
                freed=$((freed + BOOT_VOLUME_SIZE_GB))
                print_success "Will NOT preserve old boot volume — OCI replaces in-place, frees ${BOOT_VOLUME_SIZE_GB} GB"
                print_warning "No rollback possible after replacement."
                local new_strategies=() new_actions=()
                for i in "${!strategy_actions[@]}"; do
                    if [[ "${strategy_actions[$i]}" != "delete_old_bv" ]]; then
                        new_strategies+=("${strategies[$i]}")
                        new_actions+=("${strategy_actions[$i]}")
                    fi
                done
                strategies=("${new_strategies[@]}")
                strategy_actions=("${new_actions[@]}")
                ;;
            abort)
                print_info "Quota management tips:"
                print_detail "• Delete unused boot volumes: oci bv boot-volume delete --boot-volume-id <OCID>"
                print_detail "• Delete backups: oci bv boot-volume-backup delete --boot-volume-backup-id <OCID>"
                print_detail "• Check usage: oci bv boot-volume list --compartment-id <tenancy>"
                die "Not enough storage. Free up space and re-run."
                ;;
        esac
    done

    echo ""
    print_success "Storage strategy set. Proceeding with $(( available + freed )) GB available."
    log "Storage freed: ${freed}GB (skip_backup=$SKIP_BACKUP, delete_old_bv=$DELETE_OLD_BV)"
}

# ============================================================================
# Boot Volume Replacement (Atomic OCI API)
# ============================================================================

replace_boot_volume() {
    local metadata_json="$1"

    print_step "Replacing boot volume with new Ubuntu image..."
    print_info "This is an atomic operation: OCI will create a new boot volume from the image,"
    print_info "detach the old one, attach the new one, and start the instance."

    local preserve_old_bv="true"
    if $DELETE_OLD_BV; then
        preserve_old_bv="false"
        print_info "Old boot volume will NOT be preserved (quota strategy)."
    else
        print_info "Old boot volume will be preserved for rollback."
    fi

    local replace_result
    replace_result=$(oci_cmd_checked compute instance \
        update-instance-update-instance-source-via-image-details \
        --instance-id "$INSTANCE_OCID" \
        --source-details-image-id "$IMAGE_OCID" \
        --source-details-boot-volume-size-in-gbs "$BOOT_VOLUME_SIZE_GB" \
        --source-details-is-preserve-boot-volume-enabled "$preserve_old_bv" \
        --metadata "$metadata_json" \
        --force) || true

    if [[ -z "$replace_result" ]]; then
        print_error "Boot volume replacement failed."
        print_info "Your instance should still have its old boot volume attached."
        print_info "Check the OCI Console for details."
        print_detail "  Instance: $INSTANCE_OCID"
        die "Replace boot volume failed. Check OCI Console and try again."
    fi

    log "Replace boot volume command accepted."
    print_success "Replace boot volume initiated. Waiting for completion..."

    # Poll for new boot volume attachment
    local wait_elapsed=0
    local wait_max=1200
    local old_bv="$CURRENT_BOOT_VOLUME_ID"
    while (( wait_elapsed < wait_max )); do
        local current_bv
        current_bv=$(oci_cmd compute boot-volume-attachment list \
            --compartment-id "$COMPARTMENT_OCID" \
            --availability-domain "$AVAILABILITY_DOMAIN" \
            --instance-id "$INSTANCE_OCID" 2>/dev/null \
            | jq -r '[.data[] | select(.["lifecycle-state"] == "ATTACHED")] | .[0]["boot-volume-id"] // "none"')

        if [[ "$current_bv" != "none" && "$current_bv" != "$old_bv" && "$current_bv" != "null" ]]; then
            new_bv_id="$current_bv"
            break
        fi

        printf "\r    Replacing boot volume... Elapsed: %ds / %ds" "$wait_elapsed" "$wait_max"
        sleep 15
        wait_elapsed=$((wait_elapsed + 15))
    done
    echo ""

    if [[ -z "$new_bv_id" || "$new_bv_id" == "none" ]]; then
        die "Timeout waiting for boot volume replacement to complete after ${wait_max}s"
    fi

    local new_state
    new_state=$(get_instance_state)

    log "Replace boot volume complete. Instance state: $new_state, new BV: $new_bv_id"
    print_success "Boot volume replaced! New BV: $new_bv_id"
    print_detail "Instance state: $new_state"
}

# ============================================================================
# Recovery: Re-attach Boot Volume
# ============================================================================

recover_detached_boot_volume() {
    print_warning "Recovery detected: Instance is STOPPED with NO boot volume attached."
    print_info "This looks like a previous run failed after detaching the boot volume."
    print_info "The replace-boot-volume API requires an attached boot volume."
    print_info "Re-attaching old boot volume first so the replace command can proceed."
    echo ""

    local recovery_action
    recovery_action=$(prompt_selection "How would you like to proceed?" \
        "Re-attach old BV and continue with replacement" \
        "Re-attach old BV and abort (restore previous state)")

    if [[ "$recovery_action" == "1" ]]; then
        # Abort — just restore
        print_info "Re-attaching old boot volume..."
        oci_cmd_checked compute boot-volume-attachment attach \
            --boot-volume-id "$CURRENT_BOOT_VOLUME_ID" \
            --instance-id "$INSTANCE_OCID" \
            --display-name "recovery-reattach-${TIMESTAMP}" >/dev/null || true
        sleep 15
        print_success "Old boot volume re-attached. Starting instance..."
        start_instance
        print_success "Instance restored to previous state."
        return 1  # Signal caller to abort
    fi

    # Continue — re-attach so replace API works
    print_step "Re-attaching old boot volume for replacement..."
    oci_cmd_checked compute boot-volume-attachment attach \
        --boot-volume-id "$CURRENT_BOOT_VOLUME_ID" \
        --instance-id "$INSTANCE_OCID" \
        --display-name "pre-replace-reattach-${TIMESTAMP}" >/dev/null || true
    sleep 15

    local reattach_state
    reattach_state=$(oci_cmd compute boot-volume-attachment list \
        --compartment-id "$COMPARTMENT_OCID" \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --instance-id "$INSTANCE_OCID" 2>/dev/null \
        | jq -r '[.data[] | select(.["lifecycle-state"] == "ATTACHED")] | length')
    if [[ "$reattach_state" == "0" ]]; then
        print_info "Waiting for boot volume to attach..."
        sleep 30
    fi
    print_success "Old boot volume re-attached. Ready for replacement."
    return 0
}
