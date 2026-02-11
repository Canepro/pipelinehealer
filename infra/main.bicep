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
// Azure OpenAI Service
// ============================================================================
resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${resourceBaseName}-openai-${uniqueSuffix}'
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: '${resourceBaseName}-openai-${uniqueSuffix}'
    publicNetworkAccess: 'Enabled'
  }
}

// GPT-4o deployment for agent reasoning
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAiAccount
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-08-06'
    }
  }
}

// ============================================================================
// Azure Cosmos DB (for agent state and activity logs)
// ============================================================================
resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
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

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosDbAccount
  name: 'pipelinehealer'
  properties: {
    resource: {
      id: 'pipelinehealer'
    }
  }
}

resource activitiesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
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

resource workflowRunsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
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
              name: 'AZURE_OPENAI_ENDPOINT'
              value: openAiAccount.properties.endpoint
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT_NAME'
              value: gpt4oDeployment.name
            }
            {
              name: 'COSMOS_DB_ENDPOINT'
              value: cosmosDbAccount.properties.documentEndpoint
            }
            {
              name: 'COSMOS_DB_DATABASE'
              value: cosmosDatabase.name
            }
            {
              name: 'KEY_VAULT_URL'
              value: keyVault.properties.vaultUri
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
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
              name: 'API_URL'
              value: 'https://${backendApp.properties.configuration.ingress.fqdn}'
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
resource backendCosmosRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
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
resource backendOpenAiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
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
output openAiEndpoint string = openAiAccount.properties.endpoint
output cosmosDbEndpoint string = cosmosDbAccount.properties.documentEndpoint
output keyVaultUrl string = keyVault.properties.vaultUri
output appInsightsConnectionString string = appInsights.properties.ConnectionString
