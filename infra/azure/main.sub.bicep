targetScope = 'subscription'

@description('Dedicated resource group for the isolated Data Intelligence Portal live-test deployment.')
param resourceGroupName string

@description('Azure region for the dedicated resource group and child resources.')
param resourceGroupLocation string = 'uksouth'

@description('Set false to deploy shared infra only before the first image push.')
param deployApps bool = true

@description('Name of the dedicated ACR.')
param containerRegistryName string

@description('Name of the dedicated user-assigned managed identity.')
param managedIdentityName string

@description('Name of the dedicated Log Analytics workspace.')
param logAnalyticsWorkspaceName string

@description('Name of the dedicated storage account for Azure Files persistence.')
param storageAccountName string

@description('Name of the dedicated Azure Container Apps environment.')
param containerAppsEnvironmentName string

@description('Data Intelligence Portal container app name.')
param containerAppName string

@description('Existing shared Key Vault name.')
param sharedKeyVaultName string

@description('Resource group containing the shared Key Vault.')
param sharedKeyVaultResourceGroupName string

@description('Subscription containing the shared Key Vault.')
param sharedKeyVaultSubscriptionId string = subscription().subscriptionId

@description('External custom domain for the portal.')
param publicDomain string = 'dip.vendorlogic.io'

@description('Subdomain host record for the portal custom domain.')
param dnsSubdomain string = 'dip'

@description('Bind the public custom domain to the Container App. Enable only after DNS validation records exist.')
param customDomainBindingEnabled bool = false

@description('Existing managed certificate name for the public custom domain. Leave blank only when extending the template to create a new certificate.')
param managedCertificateName string = ''

@description('Container image repository prefix.')
param imageRepositoryPrefix string = 'dip'

@description('Container image tag.')
param imageTag string = '1.0.16-live-test'

@allowed([
  'DELETE'
  'TRUNCATE'
  'PERSIST'
  'MEMORY'
  'WAL'
  'OFF'
])
@description('SQLite journal mode for the MVP active database. Azure live-test runs the active DB on local container storage and persists snapshots to Azure Files.')
param sqliteJournalMode string = 'DELETE'

@description('Container CPU allocation.')
param appCpu string = '0.5'

@description('Container memory allocation.')
param appMemory string = '1Gi'

@description('Container app minimum replicas.')
param minReplicas int = 1

@description('Container app maximum replicas.')
param maxReplicas int = 1

@description('Enable Azure Container Apps built-in authentication using Microsoft Entra ID.')
param entraAuthEnabled bool = true

@description('Entra tenant ID for the app registration.')
param entraTenantId string

@description('Entra app registration client ID for Container Apps authentication.')
param entraClientId string

@description('Key Vault secret name containing the Entra app registration client secret.')
param entraClientSecretName string = 'dip-entra-client-secret'

@description('Entra admin group object ID.')
param entraAdminGroupId string

@description('Entra standard group object ID.')
param entraStandardGroupId string

@description('Seed reference configuration data on startup.')
param seedReferenceData bool = true

@description('Seed demo/sample data on startup. Keep false for live-test customer data capture.')
param seedDemoData bool = false

@description('Apply all built-in customer intelligence packs on startup to preconfigure the live-demo catalogue.')
param autoApplyCustomerPacks bool = false

@description('KRA LLM provider mode. Use disabled for deterministic local-only operation, or openai_direct for the approved live-demo OpenAI route.')
param kraLlmProvider string = 'disabled'

@description('KRA LLM model name for AI-assisted summaries.')
param kraModel string = ''

@description('KRA MCP/agent runtime mode label shown in the UI.')
param kraMcpMode string = 'local_registry'

@description('Key Vault secret name containing the KRA/OpenAI API key. Leave blank to run KRA without AI-assisted summaries.')
param kraApiKeySecretName string = ''

resource dedicatedResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: resourceGroupLocation
}

module portalStack './main.rg.bicep' = {
  name: 'dip-live-test-stack'
  scope: dedicatedResourceGroup
  params: {
    location: resourceGroupLocation
    deployApps: deployApps
    containerRegistryName: containerRegistryName
    managedIdentityName: managedIdentityName
    logAnalyticsWorkspaceName: logAnalyticsWorkspaceName
    storageAccountName: storageAccountName
    containerAppsEnvironmentName: containerAppsEnvironmentName
    containerAppName: containerAppName
    sharedKeyVaultName: sharedKeyVaultName
    sharedKeyVaultResourceGroupName: sharedKeyVaultResourceGroupName
    sharedKeyVaultSubscriptionId: sharedKeyVaultSubscriptionId
    publicDomain: publicDomain
    dnsSubdomain: dnsSubdomain
    customDomainBindingEnabled: customDomainBindingEnabled
    managedCertificateName: managedCertificateName
    imageRepositoryPrefix: imageRepositoryPrefix
    imageTag: imageTag
    sqliteJournalMode: sqliteJournalMode
    appCpu: appCpu
    appMemory: appMemory
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    entraAuthEnabled: entraAuthEnabled
    entraTenantId: entraTenantId
    entraClientId: entraClientId
    entraClientSecretName: entraClientSecretName
    entraAdminGroupId: entraAdminGroupId
    entraStandardGroupId: entraStandardGroupId
    seedReferenceData: seedReferenceData
    seedDemoData: seedDemoData
    autoApplyCustomerPacks: autoApplyCustomerPacks
    kraLlmProvider: kraLlmProvider
    kraModel: kraModel
    kraMcpMode: kraMcpMode
    kraApiKeySecretName: kraApiKeySecretName
  }
}

module sharedKeyVaultRole './modules/keyvault-secrets-user-role.bicep' = {
  name: 'dip-keyvault-secrets-user'
  scope: resourceGroup(sharedKeyVaultSubscriptionId, sharedKeyVaultResourceGroupName)
  params: {
    keyVaultName: sharedKeyVaultName
    principalId: portalStack.outputs.managedIdentityPrincipalId
  }
}

output resourceGroupName string = dedicatedResourceGroup.name
output acrName string = portalStack.outputs.acrName
output acrLoginServer string = portalStack.outputs.acrLoginServer
output storageAccountName string = portalStack.outputs.storageAccountName
output managedIdentityId string = portalStack.outputs.managedIdentityId
output managedIdentityPrincipalId string = portalStack.outputs.managedIdentityPrincipalId
output managedEnvironmentId string = portalStack.outputs.managedEnvironmentId
output managedEnvironmentName string = portalStack.outputs.managedEnvironmentName
output managedEnvironmentDefaultDomain string = portalStack.outputs.managedEnvironmentDefaultDomain
output managedEnvironmentStaticIp string = portalStack.outputs.managedEnvironmentStaticIp
output sharedKeyVaultId string = portalStack.outputs.sharedKeyVaultId
output sharedKeyVaultUri string = portalStack.outputs.sharedKeyVaultUri
output containerAppName string = portalStack.outputs.containerAppName
output containerAppFqdn string = portalStack.outputs.containerAppFqdn
output containerAppUrl string = portalStack.outputs.containerAppUrl
output dnsCnameHost string = portalStack.outputs.dnsCnameHost
output dnsCnameTarget string = portalStack.outputs.dnsCnameTarget
output dnsTxtHost string = portalStack.outputs.dnsTxtHost
output dnsTxtValue string = portalStack.outputs.dnsTxtValue
output customDomain string = portalStack.outputs.customDomain
output sharedKeyVaultSecretsUserRoleAssignmentId string = sharedKeyVaultRole.outputs.roleAssignmentId
