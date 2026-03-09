data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "target" {
  name = var.resource_group_name
}

locals {
  location           = coalesce(var.location, data.azurerm_resource_group.target.location)
  unique_suffix      = substr(md5(data.azurerm_resource_group.target.id), 0, 13)
  resource_base_name = "${var.base_name}${var.environment_name}"
  backend_image      = "${var.acr_name}.azurecr.io/${var.backend_image_name}:${var.image_tag}"
  frontend_image     = "${var.acr_name}.azurecr.io/${var.frontend_image_name}:${var.image_tag}"
  key_vault_name     = substr("${var.base_name}kv${local.unique_suffix}", 0, 24)

  acr_pull_role_definition_id       = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/7f951dda-4ed3-4680-a7ca-43fe172d538d"
  key_vault_secrets_user_role_id    = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/4633458b-17de-408a-b874-0445c86b69e6"
  cognitive_services_openai_user_id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
}

resource "azapi_resource" "openai_account" {
  type      = "Microsoft.CognitiveServices/accounts@2024-10-01"
  name      = "${local.resource_base_name}-openai-${local.unique_suffix}"
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  body = {
    kind = "OpenAI"
    sku = {
      name = "S0"
    }
    properties = {
      customSubDomainName = "${local.resource_base_name}-openai-${local.unique_suffix}"
      publicNetworkAccess = "Enabled"
    }
  }

  # These API versions are ahead of what azapi can fully validate reliably, so
  # keep schema validation disabled but export only the fields this stack reads.
  response_export_values    = ["properties.endpoint"]
  schema_validation_enabled = false
}

resource "azapi_resource" "gpt4o_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2024-10-01"
  name      = var.openai_deployment_name
  parent_id = azapi_resource.openai_account.id

  body = {
    sku = {
      name     = "Standard"
      capacity = var.openai_deployment_capacity
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = var.openai_model_name
        version = var.openai_model_version
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "cosmos_account" {
  type      = "Microsoft.DocumentDB/databaseAccounts@2024-05-15"
  name      = "${local.resource_base_name}-cosmos-${local.unique_suffix}"
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  body = {
    kind = "GlobalDocumentDB"
    properties = {
      databaseAccountOfferType = "Standard"
      consistencyPolicy = {
        defaultConsistencyLevel = "Session"
      }
      locations = [
        {
          locationName     = local.location
          failoverPriority = 0
          isZoneRedundant  = false
        }
      ]
      capabilities = [
        {
          name = "EnableServerless"
        }
      ]
    }
  }

  response_export_values    = ["properties.documentEndpoint"]
  schema_validation_enabled = false
}

resource "azapi_resource" "cosmos_database" {
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15"
  name      = "pipelinehealer"
  parent_id = azapi_resource.cosmos_account.id

  body = {
    properties = {
      resource = {
        id = "pipelinehealer"
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "activities_container" {
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15"
  name      = "activities"
  parent_id = azapi_resource.cosmos_database.id

  body = {
    properties = {
      resource = {
        id = "activities"
        partitionKey = {
          paths = ["/repositoryId"]
          kind  = "Hash"
        }
        indexingPolicy = {
          automatic    = true
          indexingMode = "consistent"
        }
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "workflow_runs_container" {
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15"
  name      = "workflow_runs"
  parent_id = azapi_resource.cosmos_database.id

  body = {
    properties = {
      resource = {
        id = "workflow_runs"
        partitionKey = {
          paths = ["/repositoryId"]
          kind  = "Hash"
        }
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "log_analytics_workspace" {
  type      = "Microsoft.OperationalInsights/workspaces@2023-09-01"
  name      = "${local.resource_base_name}-logs-${local.unique_suffix}"
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  body = {
    properties = {
      sku = {
        name = "PerGB2018"
      }
      retentionInDays = var.log_analytics_retention_days
    }
  }

  response_export_values    = ["properties.customerId"]
  schema_validation_enabled = false
}

data "azapi_resource_action" "log_analytics_shared_keys" {
  type                   = "Microsoft.OperationalInsights/workspaces@2020-08-01"
  resource_id            = azapi_resource.log_analytics_workspace.id
  action                 = "sharedKeys"
  method                 = "POST"
  response_export_values = ["primarySharedKey"]
}

resource "azapi_resource" "app_insights" {
  type      = "Microsoft.Insights/components@2020-02-02"
  name      = "${local.resource_base_name}-insights-${local.unique_suffix}"
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  body = {
    kind = "web"
    properties = {
      Application_Type    = "web"
      WorkspaceResourceId = azapi_resource.log_analytics_workspace.id
    }
  }

  response_export_values    = ["properties.ConnectionString"]
  schema_validation_enabled = false
}

resource "azapi_resource" "key_vault" {
  type      = "Microsoft.KeyVault/vaults@2023-07-01"
  name      = local.key_vault_name
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  body = {
    properties = {
      sku = {
        family = "A"
        name   = "standard"
      }
      tenantId                  = data.azurerm_client_config.current.tenant_id
      enableRbacAuthorization   = true
      enableSoftDelete          = true
      softDeleteRetentionInDays = 7
    }
  }

  response_export_values    = ["properties.vaultUri"]
  schema_validation_enabled = false
}

resource "azapi_resource" "container_registry" {
  type      = "Microsoft.ContainerRegistry/registries@2023-07-01"
  name      = var.acr_name
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  body = {
    sku = {
      name = "Basic"
    }
    properties = {
      adminUserEnabled    = false
      publicNetworkAccess = "Enabled"
    }
  }

  response_export_values    = ["properties.loginServer"]
  schema_validation_enabled = false
}

resource "azapi_resource" "acr_pull_identity" {
  type      = "Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31"
  name      = var.acr_pull_identity_name
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  response_export_values    = ["properties.principalId"]
  schema_validation_enabled = false
}

locals {
  acr_pull_role_assignment_guid = format(
    "%s-%s-%s-%s-%s",
    substr(md5("${azapi_resource.acr_pull_identity.id}/${azapi_resource.container_registry.id}/acrpull"), 0, 8),
    substr(md5("${azapi_resource.acr_pull_identity.id}/${azapi_resource.container_registry.id}/acrpull"), 8, 4),
    substr(md5("${azapi_resource.acr_pull_identity.id}/${azapi_resource.container_registry.id}/acrpull"), 12, 4),
    substr(md5("${azapi_resource.acr_pull_identity.id}/${azapi_resource.container_registry.id}/acrpull"), 16, 4),
    substr(md5("${azapi_resource.acr_pull_identity.id}/${azapi_resource.container_registry.id}/acrpull"), 20, 12)
  )
}

resource "azapi_resource" "acr_pull_role_assignment" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = local.acr_pull_role_assignment_guid
  parent_id = azapi_resource.container_registry.id

  body = {
    properties = {
      roleDefinitionId = local.acr_pull_role_definition_id
      principalId      = azapi_resource.acr_pull_identity.output.properties.principalId
      principalType    = "ServicePrincipal"
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "container_app_environment" {
  type      = "Microsoft.App/managedEnvironments@2024-03-01"
  name      = var.container_apps_environment_name
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  body = {
    properties = {
      appLogsConfiguration = {
        destination = "log-analytics"
        logAnalyticsConfiguration = {
          customerId = azapi_resource.log_analytics_workspace.output.properties.customerId
          sharedKey  = data.azapi_resource_action.log_analytics_shared_keys.output.primarySharedKey
        }
      }
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "backend_app" {
  type      = "Microsoft.App/containerApps@2024-03-01"
  name      = var.backend_container_app_name
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azapi_resource.acr_pull_identity.id]
  }

  body = {
    properties = {
      managedEnvironmentId = azapi_resource.container_app_environment.id
      configuration = {
        ingress = {
          external   = true
          targetPort = 8000
          transport  = "auto"
        }
        registries = [
          {
            server   = azapi_resource.container_registry.output.properties.loginServer
            identity = azapi_resource.acr_pull_identity.id
          }
        ]
      }
      template = {
        containers = [
          {
            name  = "backend"
            image = local.backend_image
            resources = {
              cpu    = 1
              memory = "2Gi"
            }
            env = [
              {
                name  = "ENVIRONMENT"
                value = var.environment_name == "prod" ? "production" : "development"
              },
              {
                name  = "AZURE_OPENAI_ENDPOINT"
                value = azapi_resource.openai_account.output.properties.endpoint
              },
              {
                name  = "AZURE_OPENAI_DEPLOYMENT_NAME"
                value = azapi_resource.gpt4o_deployment.name
              },
              {
                name  = "COSMOS_DB_ENDPOINT"
                value = azapi_resource.cosmos_account.output.properties.documentEndpoint
              },
              {
                name  = "COSMOS_DB_DATABASE"
                value = azapi_resource.cosmos_database.name
              },
              {
                name  = "KEY_VAULT_URL"
                value = azapi_resource.key_vault.output.properties.vaultUri
              },
              {
                name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
                value = azapi_resource.app_insights.output.properties.ConnectionString
              },
              {
                name  = "API_AUTH_KEY"
                value = var.api_auth_key
              },
              {
                name  = "ADMIN_API_KEY"
                value = var.admin_api_key
              },
              {
                name  = "GITHUB_WEBHOOK_SECRET"
                value = var.github_webhook_secret
              },
              {
                name  = "GITHUB_PERSONAL_ACCESS_TOKEN"
                value = var.github_personal_access_token
              }
            ]
          }
        ]
        scale = {
          minReplicas = 0
          maxReplicas = 5
        }
      }
    }
  }

  depends_on = [azapi_resource.acr_pull_role_assignment]

  response_export_values = [
    "identity.principalId",
    "properties.configuration.ingress.fqdn",
  ]
  schema_validation_enabled = false
}

resource "azapi_resource" "frontend_app" {
  type      = "Microsoft.App/containerApps@2024-03-01"
  name      = var.frontend_container_app_name
  parent_id = data.azurerm_resource_group.target.id
  location  = local.location
  tags      = var.tags

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azapi_resource.acr_pull_identity.id]
  }

  body = {
    properties = {
      managedEnvironmentId = azapi_resource.container_app_environment.id
      configuration = {
        ingress = {
          external   = true
          targetPort = 3000
          transport  = "auto"
        }
        registries = [
          {
            server   = azapi_resource.container_registry.output.properties.loginServer
            identity = azapi_resource.acr_pull_identity.id
          }
        ]
      }
      template = {
        containers = [
          {
            name  = "frontend"
            image = local.frontend_image
            resources = {
              cpu    = 0.5
              memory = "1Gi"
            }
            env = [
              {
                name  = "BACKEND_UPSTREAM"
                value = "https://${azapi_resource.backend_app.output.properties.configuration.ingress.fqdn}"
              },
              {
                name  = "API_AUTH_KEY"
                value = var.api_auth_key
              }
            ]
          }
        ]
        scale = {
          minReplicas = 0
          maxReplicas = 3
        }
      }
    }
  }

  depends_on = [azapi_resource.acr_pull_role_assignment]

  response_export_values    = ["properties.configuration.ingress.fqdn"]
  schema_validation_enabled = false
}

locals {
  backend_cosmos_role_assignment_guid = format(
    "%s-%s-%s-%s-%s",
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.cosmos_account.id}/cosmos-contributor"), 0, 8),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.cosmos_account.id}/cosmos-contributor"), 8, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.cosmos_account.id}/cosmos-contributor"), 12, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.cosmos_account.id}/cosmos-contributor"), 16, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.cosmos_account.id}/cosmos-contributor"), 20, 12)
  )
  backend_key_vault_role_assignment_guid = format(
    "%s-%s-%s-%s-%s",
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.key_vault.id}/keyvault-secrets"), 0, 8),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.key_vault.id}/keyvault-secrets"), 8, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.key_vault.id}/keyvault-secrets"), 12, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.key_vault.id}/keyvault-secrets"), 16, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.key_vault.id}/keyvault-secrets"), 20, 12)
  )
  backend_openai_role_assignment_guid = format(
    "%s-%s-%s-%s-%s",
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.openai_account.id}/openai-user"), 0, 8),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.openai_account.id}/openai-user"), 8, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.openai_account.id}/openai-user"), 12, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.openai_account.id}/openai-user"), 16, 4),
    substr(md5("${azapi_resource.backend_app.id}/${azapi_resource.openai_account.id}/openai-user"), 20, 12)
  )
}

resource "azapi_resource" "backend_cosmos_role_assignment" {
  type      = "Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15"
  name      = local.backend_cosmos_role_assignment_guid
  parent_id = azapi_resource.cosmos_account.id

  body = {
    properties = {
      roleDefinitionId = "${azapi_resource.cosmos_account.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
      principalId      = azapi_resource.backend_app.output.identity.principalId
      scope            = azapi_resource.cosmos_account.id
    }
  }

  depends_on = [azapi_resource.backend_app]

  schema_validation_enabled = false
}

resource "azapi_resource" "backend_key_vault_role_assignment" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = local.backend_key_vault_role_assignment_guid
  parent_id = azapi_resource.key_vault.id

  body = {
    properties = {
      roleDefinitionId = local.key_vault_secrets_user_role_id
      principalId      = azapi_resource.backend_app.output.identity.principalId
      principalType    = "ServicePrincipal"
    }
  }

  depends_on = [azapi_resource.backend_app]

  schema_validation_enabled = false
}

resource "azapi_resource" "backend_openai_role_assignment" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = local.backend_openai_role_assignment_guid
  parent_id = azapi_resource.openai_account.id

  body = {
    properties = {
      roleDefinitionId = local.cognitive_services_openai_user_id
      principalId      = azapi_resource.backend_app.output.identity.principalId
      principalType    = "ServicePrincipal"
    }
  }

  depends_on = [azapi_resource.backend_app]

  schema_validation_enabled = false
}
