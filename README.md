# IaC Cookbook - Multi-Cloud Infrastructure as Code Scripts

A comprehensive collection of Infrastructure as Code (IaC) command scripts for multiple cloud providers including OCI, GCP, Azure, AWS, and Cloudflare.

## Overview

This repository provides ready-to-use IaC scripts and templates for provisioning cloud infrastructure across different cloud providers. Starting with Oracle Cloud Infrastructure (OCI) Free Tier resources, the project aims to simplify cloud resource deployment through reusable, modular scripts.

## Project Structure

```
iac-cookbook/
├── oci/                    # Oracle Cloud Infrastructure scripts
│   └── free-tier/         # OCI Free Tier specific resources
│       ├── compute/       # Compute instances and configurations
│       ├── networking/    # VCN, subnets, security lists
│       ├── storage/       # Block volumes, object storage
│       ├── database/      # Always Free autonomous databases
│       └── scripts/       # Helper scripts and utilities
├── gcp/                   # Google Cloud Platform scripts (coming soon)
├── azure/                 # Microsoft Azure scripts (coming soon)
├── aws/                   # Amazon Web Services scripts (coming soon)
├── cloudflare/            # Cloudflare services and edge computing
│   ├── dns/              # DNS management and records
│   ├── workers/          # Workers and serverless functions
│   ├── pages/            # Pages deployments
│   ├── r2/               # R2 object storage
│   ├── d1/               # D1 database
│   ├── kv/               # KV storage
│   ├── waf/              # Web Application Firewall rules
│   ├── cdn/              # CDN and caching configurations
│   └── scripts/          # Helper scripts and utilities
└── common/                # Shared resources across clouds
    ├── templates/         # Common templates and patterns
    ├── scripts/          # Cross-cloud utility scripts
    └── docs/             # Documentation and guides
```

## Features

### OCI Free Tier Resources
- **Compute**: Provision Always Free compute instances (AMD/ARM)
- **Networking**: Setup VCNs, subnets, and security configurations
- **Storage**: Manage block volumes and object storage buckets
- **Database**: Deploy Autonomous Database instances

### Cloudflare Resources
- **DNS**: Manage DNS records and zones
- **Workers**: Deploy serverless functions at the edge
- **Pages**: Static site deployments with CI/CD
- **R2**: S3-compatible object storage
- **D1**: Serverless SQL database
- **KV**: Key-value storage at the edge
- **WAF**: Web Application Firewall rules
- **CDN**: Content delivery and caching

### Prerequisites

#### For OCI:
- OCI CLI installed and configured
- Valid OCI account with Free Tier resources available
- Terraform (optional, for Terraform-based scripts)

#### For Cloudflare:
- Cloudflare account (free tier available)
- Cloudflare API token with appropriate permissions
- Wrangler CLI for Workers deployment (optional)

## Quick Start

### OCI Free Tier Setup

1. **Configure OCI CLI**:
   ```bash
   oci setup config
   ```

2. **Set environment variables**:
   ```bash
   export OCI_TENANCY_OCID="your-tenancy-ocid"
   export OCI_USER_OCID="your-user-ocid"
   export OCI_REGION="your-region"
   ```

3. **Run scripts**:
   ```bash
   cd oci/free-tier/compute
   ./create-free-instance.sh
   ```

## Script Categories

### Infrastructure Provisioning
- Create and manage compute instances
- Network infrastructure setup
- Storage provisioning
- Database deployment

### Configuration Management
- Security configurations
- Resource tagging
- Cost optimization settings

### Maintenance & Operations
- Backup scripts
- Monitoring setup
- Resource cleanup utilities

## Contributing

Contributions are welcome! Please follow these guidelines:
1. Fork the repository
2. Create a feature branch
3. Add your scripts with proper documentation
4. Submit a pull request

## Roadmap

- [x] OCI Free Tier scripts
- [ ] Cloudflare services scripts
- [ ] GCP free tier resources
- [ ] Azure free tier resources
- [ ] AWS free tier resources
- [ ] Cross-cloud migration scripts
- [ ] Cost optimization utilities

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or contributions:
- Open an issue in the GitHub repository
- Check existing documentation in `/common/docs`
- Review examples in each cloud provider's directory

## Disclaimer

These scripts are provided as-is. Always review and test scripts in a development environment before using in production. Be aware of cloud provider pricing and free tier limitations.