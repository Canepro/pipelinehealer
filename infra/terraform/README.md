# Terraform Azure Reference Stack

This directory is the Terraform equivalent of [`../main.bicep`](../main.bicep) for the current Azure reference deployment.

It provisions the same major resources:

- Azure OpenAI account + deployment
- Cosmos DB SQL API account, database, and containers
- Log Analytics + Application Insights
- Key Vault
- Azure Container Registry
- User-assigned identity for ACR pulls
- Azure Container Apps environment
- Backend and frontend Azure Container Apps
- RBAC assignments for ACR pull, Cosmos DB, Key Vault, and Azure OpenAI

## Important Notes

- `scripts/ph.sh` and `azure.yaml` still target the Bicep path today.
- This Terraform stack is a manual alternative for teams standardizing on Terraform.
- Sensitive app settings are passed directly into the Container App definitions, so use an encrypted remote Terraform state backend.

## Usage

1. Copy the sample vars:

```bash
cp terraform.tfvars.example terraform.tfvars
```

2. Fill in the secret values and adjust names as needed.

3. Initialize and plan:

```bash
terraform init
terraform plan
```

4. Apply:

```bash
terraform apply
```

## Inputs

Primary required input:

- `resource_group_name`

Primary sensitive inputs:

- `api_auth_key`
- `admin_api_key`
- `github_webhook_secret`
- `github_personal_access_token`
