@description('The location for the Azure Container Registry')
param location string = resourceGroup().location

@description('Azure Container Registry name (global unique, lowercase alphanumeric)')
param acrName string

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

output acrName string = containerRegistry.name
output acrLoginServer string = containerRegistry.properties.loginServer
