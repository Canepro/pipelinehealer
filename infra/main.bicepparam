using './main.bicep'

param location = 'eastus2'
param environmentName = 'dev'
param baseName = 'pipelinehealer'
param acrName = readEnvironmentVariable('PH_ACR_NAME', 'pipelinehealeracr')
param containerAppsEnvironmentName = readEnvironmentVariable('PH_CONTAINER_APPS_ENVIRONMENT_NAME', 'cae-pipelinehealer-dev')
param backendContainerAppName = readEnvironmentVariable('PH_BACKEND_APP', 'pipelinehealer-backend-dev')
param frontendContainerAppName = readEnvironmentVariable('PH_FRONTEND_APP', 'pipelinehealer-frontend-dev')
param backendImageName = 'pipelinehealer-backend'
param frontendImageName = 'pipelinehealer-frontend'
param imageTag = 'latest'
param backendResources = {
  cpu: '0.5'
  memory: '1Gi'
}
param frontendResources = {
  cpu: '0.25'
  memory: '0.5Gi'
}
param apiAuthKey = readEnvironmentVariable('API_AUTH_KEY', 'replace_me_api_auth_key')
param adminApiKey = readEnvironmentVariable('ADMIN_API_KEY', 'replace_me_admin_api_key')
param githubWebhookSecret = readEnvironmentVariable('GITHUB_WEBHOOK_SECRET', 'replace_me_webhook_secret')
param githubPersonalAccessToken = readEnvironmentVariable('GITHUB_PERSONAL_ACCESS_TOKEN', '')
