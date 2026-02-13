using './main.bicep'

param location = 'eastus2'
param environmentName = 'dev'
param baseName = 'pipelinehealer'
param acrName = 'caneprophacr01'
param containerAppsEnvironmentName = 'cae-canepro-ph-dev-eus'
param backendContainerAppName = 'ca-canepro-ph-backend'
param frontendContainerAppName = 'ca-canepro-ph-frontend'
param backendImageName = 'pipelinehealer-backend'
param frontendImageName = 'pipelinehealer-frontend'
param imageTag = 'latest'
param apiAuthKey = readEnvironmentVariable('API_AUTH_KEY', 'replace_me_api_auth_key')
param adminApiKey = readEnvironmentVariable('ADMIN_API_KEY', 'replace_me_admin_api_key')
param githubWebhookSecret = readEnvironmentVariable('GITHUB_WEBHOOK_SECRET', 'replace_me_webhook_secret')
param githubPersonalAccessToken = readEnvironmentVariable('GITHUB_PERSONAL_ACCESS_TOKEN', '')
