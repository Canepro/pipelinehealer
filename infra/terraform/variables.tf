variable "resource_group_name" {
  description = "Existing Azure resource group that will own the deployed resources."
  type        = string
}

variable "location" {
  description = "Azure region for all resources. Defaults to the target resource group's location when null."
  type        = string
  default     = null
}

variable "environment_name" {
  description = "Environment name (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "base_name" {
  description = "Base name for generated resources."
  type        = string
  default     = "pipelinehealer"
}

variable "acr_name" {
  description = "Azure Container Registry name. Must be globally unique, lowercase, and alphanumeric."
  type        = string
  default     = "pipelinehealeracr"
}

variable "container_apps_environment_name" {
  description = "Container Apps environment name."
  type        = string
  default     = "cae-pipelinehealer-dev"
}

variable "backend_container_app_name" {
  description = "Backend Container App name."
  type        = string
  default     = "pipelinehealer-backend-dev"
}

variable "frontend_container_app_name" {
  description = "Frontend Container App name."
  type        = string
  default     = "pipelinehealer-frontend-dev"
}

variable "backend_image_name" {
  description = "Backend image repository name in ACR."
  type        = string
  default     = "pipelinehealer-backend"
}

variable "frontend_image_name" {
  description = "Frontend image repository name in ACR."
  type        = string
  default     = "pipelinehealer-frontend"
}

variable "image_tag" {
  description = "Container image tag for backend and frontend."
  type        = string
  default     = "latest"
}

variable "api_auth_key" {
  description = "API key for X-API-Key protected /api/* routes."
  type        = string
  sensitive   = true
}

variable "admin_api_key" {
  description = "Admin API key for X-Admin-Key protected /api/settings* routes."
  type        = string
  sensitive   = true
}

variable "github_webhook_secret" {
  description = "GitHub webhook secret used to validate webhook signatures."
  type        = string
  sensitive   = true
}

variable "github_personal_access_token" {
  description = "GitHub PAT for API access. Leave empty when using GitHub App auth only."
  type        = string
  default     = ""
  sensitive   = true
}

variable "acr_pull_identity_name" {
  description = "User-assigned identity name used by Container Apps to pull from ACR."
  type        = string
  default     = "id-pipelinehealer-acrpull"
}

variable "openai_deployment_name" {
  description = "Azure OpenAI deployment name exposed to the backend."
  type        = string
  default     = "gpt-4o"
}

variable "openai_model_name" {
  description = "Azure OpenAI base model name."
  type        = string
  default     = "gpt-4o"
}

variable "openai_model_version" {
  description = "Azure OpenAI model version."
  type        = string
  default     = "2024-08-06"
}

variable "openai_deployment_capacity" {
  description = "Azure OpenAI deployment capacity."
  type        = number
  default     = 30
}

variable "log_analytics_retention_days" {
  description = "Log Analytics retention in days."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Optional Azure tags applied to top-level resources."
  type        = map(string)
  default     = {}
}
