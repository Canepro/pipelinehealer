output "acr_name" {
  description = "Azure Container Registry name."
  value       = azapi_resource.container_registry.name
}

output "acr_login_server" {
  description = "Azure Container Registry login server."
  value       = azapi_resource.container_registry.output.properties.loginServer
}

output "backend_app_name" {
  description = "Backend Container App name."
  value       = azapi_resource.backend_app.name
}

output "backend_url" {
  description = "Backend HTTPS endpoint."
  value       = "https://${azapi_resource.backend_app.output.properties.configuration.ingress.fqdn}"
}

output "frontend_app_name" {
  description = "Frontend Container App name."
  value       = azapi_resource.frontend_app.name
}

output "frontend_url" {
  description = "Frontend HTTPS endpoint."
  value       = "https://${azapi_resource.frontend_app.output.properties.configuration.ingress.fqdn}"
}

output "openai_endpoint" {
  description = "Azure OpenAI endpoint."
  value       = azapi_resource.openai_account.output.properties.endpoint
}

output "cosmos_db_endpoint" {
  description = "Cosmos DB SQL API endpoint."
  value       = azapi_resource.cosmos_account.output.properties.documentEndpoint
}

output "key_vault_url" {
  description = "Key Vault URI."
  value       = azapi_resource.key_vault.output.properties.vaultUri
}

output "app_insights_connection_string" {
  description = "Application Insights connection string."
  value       = azapi_resource.app_insights.output.properties.ConnectionString
  sensitive   = true
}
