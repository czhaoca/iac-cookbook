# OCI Block Volume Strategy — Boot vs. Block Storage for VM Reprovisioning

> **Decision Record** — Why we separate persistent data from boot volumes in OCI free-tier VMs.

## Problem Statement

When reprovisioning an OCI VM (replacing the boot volume with a fresh OS image), **all data on the boot volume is destroyed**. This includes application data, databases, user uploads, and configuration. We need a strategy to persist important data across OS upgrades and reprovisioning events without exceeding OCI free-tier storage limits.

## Options Considered

### Option A: Boot Volume Only (Current)

Everything lives on the 47–50 GB boot volume. On reprovision, data is lost unless manually backed up beforehand.

### Option B: Separate Block Volume for Persistent Data (Recommended)

Attach a dedicated block volume to each VM. Mount it at a path like `/data`. Store databases, uploads, configs, and application state there. On reprovision, detach the block volume, replace the boot volume, re-attach the block volume.

### Option C: Object Storage for Backups

Use OCI Object Storage (free tier: 10 GB standard, 10 GB infrequent access) to periodically back up data. Restore after reprovisioning.

## Decision: Option B — Separate Block Volume

Block volumes provide **real-time persistent storage** that survives boot volume replacement without requiring backup/restore cycles. Object Storage (Option C) is complementary for off-instance backups but not a substitute for live storage.

## OCI Free Tier Storage Budget

Per the [OCI Always Free Resources documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm):

| Resource | Free Tier Allowance |
|----------|-------------------|
| Total block storage | **200 GB** per availability domain |
| Includes | Boot volumes + block volumes + boot volume backups |
| Object Storage | 10 GB Standard + 10 GB Infrequent Access |
| Max volume attachments per VM | 32 (iSCSI) or 16 (paravirtualized) |

### Storage Budget for 3 Free-Tier VMs

| VM | Shape | Boot Vol | Block Vol (data) | Total |
|----|-------|----------|-----------------|-------|
| vm-arm-1 | A1.Flex (ARM) | 47 GB | 20 GB | 67 GB |
| vm-x86-1 | E2.1.Micro (x86) | 47 GB | 10 GB | 57 GB |
| vm-x86-2 | E2.1.Micro (x86) | 47 GB | 10 GB | 57 GB |
| **Total** | | **141 GB** | **40 GB** | **181 GB** |

This leaves **19 GB headroom** under the 200 GB limit — enough for one boot volume backup if needed during a reprovision cycle, but tight. Adjust block volume sizes based on actual usage.

**Alternative tighter config** (if headroom is critical):

| VM | Boot Vol | Block Vol | Total |
|----|----------|-----------|-------|
| vm-arm-1 | 47 GB | 15 GB | 62 GB |
| vm-x86-1 | 47 GB | 5 GB | 52 GB |
| vm-x86-2 | 47 GB | 5 GB | 52 GB |
| **Total** | 141 GB | 25 GB | **166 GB** (34 GB headroom) |

## Can Multiple VMs Share One Block Volume?

**Short answer: Not simultaneously in free tier.**

Per the [OCI Block Volume overview](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/overview.htm):

- **Read/Write multi-attach** exists but requires a cluster-aware filesystem (e.g., OCFS2, GFS2) and is designed for paid bare metal / high-OCPU VMs.
- **Cross-architecture sharing** (ARM A1 ↔ x86 Micro) is architecturally possible (same availability domain, same subnet), but:
  - Multi-attach is not available for free-tier shapes (requires 16+ OCPUs for multipath).
  - A block volume can only be attached to **one instance at a time** in read/write mode on standard VMs.
- **Sequential sharing** works fine: detach from VM-A, attach to VM-B. But this requires downtime.

**Recommendation**: Give each VM its own block volume. The storage overhead is modest (5–20 GB each) and avoids the complexity of shared filesystems.

## Performance Characteristics

Per the [OCI Block Volume Performance documentation](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumeperformance.htm):

| Shape | Max IOPS | Max Throughput | Attachment Types |
|-------|----------|----------------|-----------------|
| A1.Flex (ARM, 4 OCPU) | 80,000 | 480 MB/s | iSCSI or Paravirtualized |
| E2.1.Micro (x86, 1 OCPU) | 6,000 | 60 MB/s | iSCSI or Paravirtualized |

### Latency Considerations

- **Boot volume** (paravirtualized): Lowest latency — directly presented to the instance by the hypervisor. Sub-millisecond for cached reads.
- **Block volume** (paravirtualized): Same performance tier as boot volume. OCI block volumes are network-attached but paravirtualized attachment achieves near-local latency.
- **Block volume** (iSCSI): Slightly higher latency (~0.1–0.5ms overhead) but supports more volumes per instance (32 vs 16). Requires manual `iscsiadm` setup or the OCI Block Volume Management plugin.

**For free-tier VMs**, paravirtualized attachment is recommended — simpler setup (auto-detected by OS), no iSCSI config needed, and the E2.1.Micro shape's 480 Mbps network bandwidth is the real bottleneck, not attachment type.

### Block Volume Performance Tiers

OCI offers performance tiers for block volumes. Free-tier volumes default to the **Balanced** tier:

| Tier | IOPS/GB | Throughput/GB | Cost |
|------|---------|---------------|------|
| Lower Cost | 2 | 240 KB/s | Included in free tier |
| Balanced | 60 | 480 KB/s | Included in free tier |
| Higher Performance | 75 | 600 KB/s | Paid only |
| Ultra High Performance | 90–225 | varies | Paid only |

For a 10 GB block volume on Balanced tier: 600 IOPS, 4.8 MB/s — more than sufficient for config files, small databases, and app data on a micro instance.

## Implementation Plan

### 1. Create Block Volumes (one per VM)

```bash
oci bv volume create \
  --compartment-id <compartment-ocid> \
  --availability-domain <ad> \
  --display-name "vm-arm-1-data" \
  --size-in-gbs 20 \
  --vpus-per-gb 10  # Balanced tier
```

### 2. Attach to Instance (paravirtualized)

```bash
oci compute volume-attachment attach \
  --instance-id <instance-ocid> \
  --volume-id <volume-ocid> \
  --type paravirtualized \
  --display-name "vm-arm-1-data-attach"
```

### 3. Mount on the Instance

```bash
# Find the device (usually /dev/sdb for first attached volume)
sudo lsblk

# First time: format and mount
sudo mkfs.ext4 /dev/sdb
sudo mkdir -p /data
sudo mount /dev/sdb /data

# Persistent mount via /etc/fstab (use UUID, not device path)
UUID=$(sudo blkid -s UUID -o value /dev/sdb)
echo "UUID=$UUID /data ext4 defaults,_netdev,nofail 0 2" | sudo tee -a /etc/fstab
```

Key fstab options per [OCI docs](https://docs.oracle.com/en-us/iaas/Content/Block/References/fstaboptions.htm):
- `_netdev` — wait for network before mounting (required for network-attached volumes)
- `nofail` — don't block boot if volume is unavailable

### 4. Cloud-Init Integration

Add block volume mount to the cloud-init user-data so it auto-mounts after reprovisioning:

```yaml
runcmd:
  - |
    # Auto-mount existing data volume if attached
    DATA_DEV=$(lsblk -dpno NAME,TYPE | grep disk | grep -v $(findmnt -n -o SOURCE / | sed 's/[0-9]*$//') | head -1 | awk '{print $1}')
    if [ -n "$DATA_DEV" ]; then
      mkdir -p /data
      # Only format if no filesystem exists
      if ! blkid "$DATA_DEV" | grep -q TYPE; then
        mkfs.ext4 "$DATA_DEV"
      fi
      mount "$DATA_DEV" /data
      UUID=$(blkid -s UUID -o value "$DATA_DEV")
      grep -q "$UUID" /etc/fstab || echo "UUID=$UUID /data ext4 defaults,_netdev,nofail 0 2" >> /etc/fstab
    fi
```

### 5. Reprovision Workflow (Updated)

1. **Detach block volume** (or leave attached — block volumes persist across boot volume replacement via the atomic API)
2. **Replace boot volume** using `oci compute instance update-instance-update-instance-source-via-image-details`
3. **Cloud-init auto-mounts** the block volume on first boot
4. **Data is intact** — no backup/restore needed

## Trade-offs Summary

| Factor | Boot-Only | Boot + Block Volume |
|--------|-----------|-------------------|
| **Data safety on reprovision** | ❌ Data lost | ✅ Data persists |
| **Free-tier storage usage** | 141 GB (3 VMs) | 166–181 GB (3 VMs) |
| **Complexity** | Simple | Moderate (mount, fstab) |
| **Latency** | Lowest | Near-identical (paravirtualized) |
| **Multi-VM sharing** | N/A | Sequential only (free tier) |
| **Backup flexibility** | Must backup entire BV | Can backup just data vol |
| **Max volumes per VM** | 1 (boot) | 17 (1 boot + 16 paravirt) |

## References

- [OCI Block Volume Overview](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/overview.htm)
- [OCI Boot Volumes](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/bootvolumes.htm)
- [OCI Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [OCI Block Volume Performance](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumeperformance.htm)
- [Attaching a Block Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/attachingavolume.htm)
- [fstab Options for Block Volumes](https://docs.oracle.com/en-us/iaas/Content/Block/References/fstaboptions.htm)
- [Consistent Device Paths](https://docs.oracle.com/en-us/iaas/Content/Block/References/consistentdevicepaths.htm)
