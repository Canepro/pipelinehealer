// PipelineHealer Infrastructure
// Azure resources for the self-healing CI/CD agent system

@description('The location for all resources')
param location string = resourceGroup().location

@description('Environment name (dev, staging, prod)')
param environmentName string = 'dev'

@description('Base name for all resources')
param baseName string = 'pipelinehealer'

@description('Azure Container Registry name (global unique, lowercase alphanumeric)')
param acrName string = 'caneprophacr01'

@description('Container Apps environment name')
param containerAppsEnvironmentName string = 'cae-canepro-ph-dev-eus'

@description('Backend Container App name')
param backendContainerAppName string = 'ca-canepro-ph-backend'

@description('Frontend Container App name')
param frontendContainerAppName string = 'ca-canepro-ph-frontend'

@description('Backend image repository name in ACR')
param backendImageName string = 'pipelinehealer-backend'

@description('Frontend image repository name in ACR')
param frontendImageName string = 'pipelinehealer-frontend'

@description('Image tag for backend/frontend images')
param imageTag string = 'latest'

@description('Storage backend mode exposed to the backend. Empty keeps the app default: memory in dev, Cosmos DB otherwise.')
@allowed([
  ''
  'memory'
  'cosmos'
  'postgres'
])
param storageMode string = ''

@description('Create a managed Cosmos DB account and containers. Disable when production must preserve and use an existing Cosmos DB account.')
param createCosmosDb bool = true

@description('Cosmos DB database name used by PipelineHealer.')
param cosmosDbDatabaseName string = 'pipelinehealer'

@description('Existing Cosmos DB endpoint override. Leave empty to use the Cosmos account created by this deployment.')
param cosmosDbEndpointOverride string = ''

@description('Create a managed Azure AI/OpenAI account and model deployment. Disable when an external provider such as Codex App Server is the production model route.')
param createAzureOpenAi bool = true

@description('Managed Azure AI/OpenAI account kind when createAzureOpenAi is true.')
@allowed([
  'AIServices'
  'OpenAI'
])
param azureOpenAiAccountKind string = 'AIServices'

@description('Azure AI/OpenAI deployment name exposed to the backend when createAzureOpenAi is true, or an existing deployment name when using an external account.')
param azureOpenAiDeploymentName string = 'gpt-5.4'

@description('Azure AI/OpenAI base model name for the managed deployment.')
param azureOpenAiModelName string = 'gpt-5.4'

@description('Azure AI/OpenAI model version for the managed deployment.')
param azureOpenAiModelVersion string = '2026-03-05'

@description('Azure AI/OpenAI deployment capacity for the managed deployment.')
param azureOpenAiDeploymentCapacity int = 100

@description('Azure AI/OpenAI deployment SKU for the managed model.')
@allowed([
  'Standard'
  'GlobalStandard'
  'DataZoneStandard'
  'ProvisionedManaged'
])
param azureOpenAiDeploymentSkuName string = 'GlobalStandard'

@description('Existing Azure AI/OpenAI endpoint to expose when createAzureOpenAi is false. Leave empty when the selected LLM provider does not need Azure OpenAI.')
param azureOpenAiEndpoint string = ''

@description('Backend LLM provider route.')
@allowed([
  'azure_openai'
  'openai_compatible'
  'codex_app_server'
  'custom'
])
param llmProvider string = 'azure_openai'

@description('Codex App Server transport used when llmProvider is codex_app_server.')
@allowed([
  'stdio'
  'websocket'
])
param codexAppServerTransport string = 'stdio'

@description('Command used when Codex App Server transport is stdio.')
param codexAppServerCommand string = 'codex app-server'

@description('Codex model requested from Codex App Server.')
param codexAppServerModel string = 'gpt-5.4'

@description('Codex App Server turn timeout in milliseconds.')
param codexAppServerTurnTimeoutMs int = 120000

@description('Codex App Server WebSocket URL used when transport is websocket.')
param codexAppServerWsUrl string = ''

@description('Allow non-loopback Codex App Server WebSocket URLs. Required for ACA to call an external bridge.')
param codexAppServerWsAllowRemote bool = false

@secure()
@description('Optional bearer token for the Codex App Server WebSocket bridge.')
param codexAppServerWsBearerToken string = ''

@secure()
@description('API key for X-API-Key protected /api/* routes')
param apiAuthKey string = ''

@description('Backend authentication mode for /api routes.')
@allowed([
  'api_key'
  'entra'
  'hybrid'
])
param authMode string = 'api_key'

@description('Microsoft Entra tenant ID for backend bearer-token validation.')
param entraTenantId string = ''

@description('Microsoft Entra API app client ID used for backend token audience defaults.')
param entraClientId string = ''

@description('Optional accepted JWT audience values for Entra bearer tokens.')
param entraAllowedAudiences string = ''

@description('Accepted Entra app-role or scope values for admin-only settings endpoints.')
param entraAdminRoles string = 'PipelineHealer.Admin'

@description('Frontend session auth mode.')
@allowed([
  'none'
  'entra'
])
param frontendAuthMode string = 'none'

@description('Frontend Microsoft Entra tenant ID.')
param frontendEntraTenantId string = ''

@description('Frontend Microsoft Entra SPA client ID.')
param frontendEntraClientId string = ''

@description('Frontend Microsoft Entra authority URL.')
param frontendEntraAuthority string = ''

@description('Frontend Microsoft Entra API access scope.')
param frontendEntraApiScope string = ''

@description('Frontend Microsoft Entra redirect URI.')
param frontendEntraRedirectUri string = ''

@description('Frontend Microsoft Entra post-logout redirect URI.')
param frontendEntraPostLogoutRedirectUri string = ''

@secure()
@description('Admin API key for X-Admin-Key protected /api/settings* routes')
param adminApiKey string = ''

@secure()
@description('GitHub webhook secret used to validate webhook signatures')
param githubWebhookSecret string = ''

@secure()
@description('GitHub PAT for API access (leave empty when using GitHub App auth only)')
param githubPersonalAccessToken string = ''

@description('User-assigned identity name used by Container Apps to pull from ACR')
param acrPullIdentityName string = 'id-canepro-ph-acrpull'

// Generate unique suffix for globally unique names
var uniqueSuffix = uniqueString(resourceGroup().id)
var resourceBaseName = '${baseName}${environmentName}'
var backendImage = '${acrName}.azurecr.io/${backendImageName}:${imageTag}'
var frontendImage = '${acrName}.azurecr.io/${frontendImageName}:${imageTag}'
// Key Vault names must be 3-24 chars and alphanumeric/hyphen.
// Use a compact deterministic name to stay within limits.
var keyVaultName = take('${baseName}kv${uniqueSuffix}', 24)

// ============================================================================
// Azure AI/OpenAI Service
// ============================================================================
resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = if (createAzureOpenAi) {
  name: '${resourceBaseName}-openai-${uniqueSuffix}'
  location: location
  kind: azureOpenAiAccountKind
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: '${resourceBaseName}-openai-${uniqueSuffix}'
    publicNetworkAccess: 'Enabled'
  }
}

// Optional managed deployment for agent reasoning. Production can disable this
// when the model route is Codex App Server or another external provider.
resource managedModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (createAzureOpenAi) {
  parent: openAiAccount
  name: azureOpenAiDeploymentName
  sku: {
    name: azureOpenAiDeploymentSkuName
    capacity: azureOpenAiDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: azureOpenAiModelName
      version: azureOpenAiModelVersion
    }
  }
}

// ============================================================================
// Azure Cosmos DB (for agent state and activity logs)
// ============================================================================
resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = if (createCosmosDb) {
  name: '${resourceBaseName}-cosmos-${uniqueSuffix}'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = if (createCosmosDb) {
  parent: cosmosDbAccount
  name: cosmosDbDatabaseName
  properties: {
    resource: {
      id: cosmosDbDatabaseName
    }
  }
}

resource activitiesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = if (createCosmosDb) {
  parent: cosmosDatabase
  name: 'activities'
  properties: {
    resource: {
      id: 'activities'
      partitionKey: {
        paths: ['/repositoryId']
        kind: 'Hash'
      }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
      }
    }
  }
}

resource workflowRunsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = if (createCosmosDb) {
  parent: cosmosDatabase
  name: 'workflow_runs'
  properties: {
    resource: {
      id: 'workflow_runs'
      partitionKey: {
        paths: ['/repositoryId']
        kind: 'Hash'
      }
    }
  }
}

// ============================================================================
// Application Insights (for observability)
// ============================================================================
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${resourceBaseName}-logs-${uniqueSuffix}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${resourceBaseName}-insights-${uniqueSuffix}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
  }
}

// ============================================================================
// Azure Key Vault (for secrets management)
// ============================================================================
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// ============================================================================
// Azure Container Registry
// ============================================================================
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

// Pre-created identity for ACR pulls (avoids circular dependency during app creation).
resource acrPullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: acrPullIdentityName
  location: location
}

resource acrPullIdentityRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrPullIdentity.id, containerRegistry.id, 'acrpull')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: acrPullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Azure Container Apps Environment (for dashboard and agents)
// ============================================================================
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppsEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

// ============================================================================
// Container App for Backend API + Agents
// ============================================================================
resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendContainerAppName
  location: location
  dependsOn: [
    acrPullIdentityRoleAssignment
  ]
  identity: {
    type: 'SystemAssigned,UserAssigned'
    userAssignedIdentities: {
      '${acrPullIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: acrPullIdentity.id
        }
      ]
      secrets: concat(
        [
          {
            name: 'api-auth-key'
            value: apiAuthKey
          }
          {
            name: 'admin-api-key'
            value: adminApiKey
          }
          {
            name: 'github-webhook-secret'
            value: githubWebhookSecret
          }
        ],
        empty(githubPersonalAccessToken)
          ? []
          : [
              {
                name: 'github-personal-access-token'
                value: githubPersonalAccessToken
              }
            ],
        empty(codexAppServerWsBearerToken)
          ? []
          : [
              {
                name: 'codex-app-server-ws-bearer-token'
                value: codexAppServerWsBearerToken
              }
            ]
      )
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: {
            cpu: json('1')
            memory: '2Gi'
          }
          env: [
            {
              name: 'ENVIRONMENT'
              value: environmentName == 'prod' ? 'production' : 'development'
            }
            {
              name: 'STORAGE_MODE'
              value: storageMode
            }
            {
              name: 'LLM_PROVIDER'
              value: llmProvider
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: createAzureOpenAi ? openAiAccount!.properties.endpoint : azureOpenAiEndpoint
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT_NAME'
              value: createAzureOpenAi ? managedModelDeployment.name : azureOpenAiDeploymentName
            }
            {
              name: 'CODEX_APP_SERVER_TRANSPORT'
              value: codexAppServerTransport
            }
            {
              name: 'CODEX_APP_SERVER_COMMAND'
              value: codexAppServerCommand
            }
            {
              name: 'CODEX_APP_SERVER_MODEL'
              value: codexAppServerModel
            }
            {
              name: 'CODEX_APP_SERVER_TURN_TIMEOUT_MS'
              value: string(codexAppServerTurnTimeoutMs)
            }
            {
              name: 'CODEX_APP_SERVER_WS_URL'
              value: codexAppServerWsUrl
            }
            {
              name: 'CODEX_APP_SERVER_WS_ALLOW_REMOTE'
              value: codexAppServerWsAllowRemote ? 'true' : 'false'
            }
            {
              name: 'COSMOS_DB_ENDPOINT'
              value: empty(cosmosDbEndpointOverride) ? cosmosDbAccount!.properties.documentEndpoint : cosmosDbEndpointOverride
            }
            {
              name: 'COSMOS_DB_DATABASE'
              value: cosmosDbDatabaseName
            }
            {
              name: 'KEY_VAULT_URL'
              value: keyVault.properties.vaultUri
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
            {
              name: 'API_AUTH_KEY'
              secretRef: 'api-auth-key'
            }
            {
              name: 'ADMIN_API_KEY'
              secretRef: 'admin-api-key'
            }
            {
              name: 'AUTH_MODE'
              value: authMode
            }
            {
              name: 'ENTRA_TENANT_ID'
              value: entraTenantId
            }
            {
              name: 'ENTRA_CLIENT_ID'
              value: entraClientId
            }
            {
              name: 'ENTRA_ALLOWED_AUDIENCES'
              value: entraAllowedAudiences
            }
            {
              name: 'ENTRA_ADMIN_ROLES'
              value: entraAdminRoles
            }
            {
              name: 'GITHUB_WEBHOOK_SECRET'
              secretRef: 'github-webhook-secret'
            }
            ...(empty(githubPersonalAccessToken)
              ? []
              : [
                  {
                    name: 'GITHUB_PERSONAL_ACCESS_TOKEN'
                    secretRef: 'github-personal-access-token'
                  }
                ])
            ...(empty(codexAppServerWsBearerToken)
              ? []
              : [
                  {
                    name: 'CODEX_APP_SERVER_WS_BEARER_TOKEN'
                    secretRef: 'codex-app-server-ws-bearer-token'
                  }
                ])
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 5
      }
    }
  }
}

// ============================================================================
// Container App for Frontend Dashboard
// ============================================================================
resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: frontendContainerAppName
  location: location
  dependsOn: [
    acrPullIdentityRoleAssignment
  ]
  identity: {
    type: 'SystemAssigned,UserAssigned'
    userAssignedIdentities: {
      '${acrPullIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: acrPullIdentity.id
        }
      ]
      secrets: [
        {
          name: 'api-auth-key'
          value: apiAuthKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'BACKEND_UPSTREAM'
              value: 'https://${backendApp.properties.configuration.ingress.fqdn}'
            }
            ...(frontendAuthMode == 'entra'
              ? [
                  {
                    name: 'API_AUTH_KEY'
                    value: 'disabled'
                  }
                ]
              : [
                  {
                    name: 'API_AUTH_KEY'
                    secretRef: 'api-auth-key'
                  }
                ])
            {
              name: 'VITE_AUTH_MODE'
              value: frontendAuthMode
            }
            {
              name: 'VITE_ENTRA_TENANT_ID'
              value: frontendEntraTenantId
            }
            {
              name: 'VITE_ENTRA_CLIENT_ID'
              value: frontendEntraClientId
            }
            {
              name: 'VITE_ENTRA_AUTHORITY'
              value: frontendEntraAuthority
            }
            {
              name: 'VITE_ENTRA_API_SCOPE'
              value: frontendEntraApiScope
            }
            {
              name: 'VITE_ENTRA_REDIRECT_URI'
              value: frontendEntraRedirectUri
            }
            {
              name: 'VITE_ENTRA_POST_LOGOUT_REDIRECT_URI'
              value: frontendEntraPostLogoutRedirectUri
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
      }
    }
  }
}

// ============================================================================
// Role Assignments
// ============================================================================

// Backend App -> Cosmos DB Data Contributor
resource backendCosmosRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (createCosmosDb) {
  parent: cosmosDbAccount
  name: guid(backendApp.id, cosmosDbAccount.id, 'cosmos-contributor')
  properties: {
    roleDefinitionId: '${cosmosDbAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: backendApp.identity.principalId
    scope: cosmosDbAccount.id
  }
}

// Backend App -> Key Vault Secrets User
resource backendKeyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(backendApp.id, keyVault.id, 'keyvault-secrets')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: backendApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend App -> Azure OpenAI User
resource backendOpenAiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (createAzureOpenAi) {
  name: guid(backendApp.id, openAiAccount.id, 'openai-user')
  scope: openAiAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: backendApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend/Frontend ACR pull is granted through the shared user-assigned identity.

// ============================================================================
// Outputs
// ============================================================================
output acrName string = containerRegistry.name
output acrLoginServer string = containerRegistry.properties.loginServer
output backendAppName string = backendApp.name
output backendUrl string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output frontendAppName string = frontendApp.name
output frontendUrl string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'
output openAiEndpoint string = createAzureOpenAi ? openAiAccount!.properties.endpoint : azureOpenAiEndpoint
output cosmosDbEndpoint string = empty(cosmosDbEndpointOverride) ? cosmosDbAccount!.properties.documentEndpoint : cosmosDbEndpointOverride
output keyVaultUrl string = keyVault.properties.vaultUri
output appInsightsConnectionString string = appInsights.properties.ConnectionString
