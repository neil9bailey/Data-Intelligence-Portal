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
param imageTag string = '1.0.64-cof-archive-cleanup'

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
param appCpu string = '2.0'

@description('Container memory allocation.')
param appMemory string = '4Gi'

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

@description('Optional Entra auditor group object ID.')
param entraAuditorGroupId string = ''

@description('Optional JSON mapping that scopes standard users or groups to customer/business-unit IDs.')
param accessScopesJson string = ''

@description('Seed reference configuration data on startup.')
param seedReferenceData bool = true

@description('Seed demo/sample data on startup. Keep false for live-test customer data capture.')
param seedDemoData bool = false

@description('Apply all built-in customer intelligence packs on startup to preconfigure the Live showcase catalogue.')
param autoApplyCustomerPacks bool = false

@description('KRA LLM provider mode. Use disabled for deterministic local-only operation, or openai_direct for the approved Live showcase OpenAI route.')
param kraLlmProvider string = 'disabled'

@description('KRA LLM model name for AI-assisted summaries.')
param kraModel string = ''

@description('KRA MCP/agent runtime mode label shown in the UI.')
param kraMcpMode string = 'local_registry'

@description('Key Vault secret name containing the KRA/OpenAI API key. Leave blank to run KRA without AI-assisted summaries.')
param kraApiKeySecretName string = ''

@description('Public notice results per source page for live source checks and KRA. Keep low for current-opportunity demo cycles on Consumption Container Apps.')
param noticePageLimit string = '10'

@description('Maximum public notice pages to request during normal live source checks.')
param noticeMaxPages string = '1'

@description('Public notice lookback window in days for the current-opportunity live profile.')
param noticeLookbackDays string = '45'

@description('Maximum number of COF customers to run live KRA source research for during Autopilot. Use 0 for the current cost-controlled deterministic profile.')
param autopilotKraCustomerLimit string = '3'

@description('Maximum source pages per live KRA research run.')
param autopilotKraMaxPages string = '1'

@description('Maximum candidates per source page during live KRA research.')
param autopilotKraCandidatesPerPage string = '10'

@description('Enable broad public-market keyword sweep during Autopilot. Keep false for the current cost-controlled live profile.')
param autopilotMarketSweepEnabled bool = false

@description('Maximum keyword sweep candidates to process when the market sweep is enabled.')
param autopilotMarketSweepLimit string = '10'

@description('Comma-separated keyword sweep terms used only when the market sweep is enabled.')
param autopilotMarketSweepKeywords string = 'cyber security,IT services,traffic management,CCTV'

@description('Enable extra Autopilot classification pass. Keep false unless validating a larger live cycle.')
param autopilotClassificationEnabled bool = false

@description('Default email delivery mode for the live showcase. Use file_outbox until an approved SMTP sender is configured.')
param emailDeliveryMode string = 'file_outbox'

@description('Default sender display name used by the report email workflow.')
param emailSenderName string = 'Contracted Opportunity Finder'

@description('Default sender address used by the report email workflow.')
param emailSender string = 'no-reply@vendorlogic.io'

@description('Default report recipients for the autonomous workflow.')
param emailDefaultRecipients string = ''

@description('SMTP host for live email delivery when enabled.')
param smtpHost string = ''

@description('SMTP port for live email delivery when enabled.')
param smtpPort string = '587'

@description('SMTP username for live email delivery when enabled.')
param smtpUsername string = ''

@description('Key Vault secret name containing the SMTP password/API key. Leave blank for file-outbox safe mode.')
param smtpPasswordSecretName string = ''

@description('Whether SMTP should use STARTTLS.')
param smtpUseTls bool = true

@description('Whether SMTP sending is enabled. Keep false unless SMTP credentials are configured and approved.')
param smtpEnabled bool = false

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
    entraAuditorGroupId: entraAuditorGroupId
    accessScopesJson: accessScopesJson
    seedReferenceData: seedReferenceData
    seedDemoData: seedDemoData
    autoApplyCustomerPacks: autoApplyCustomerPacks
    kraLlmProvider: kraLlmProvider
    kraModel: kraModel
    kraMcpMode: kraMcpMode
    kraApiKeySecretName: kraApiKeySecretName
    noticePageLimit: noticePageLimit
    noticeMaxPages: noticeMaxPages
    noticeLookbackDays: noticeLookbackDays
    autopilotKraCustomerLimit: autopilotKraCustomerLimit
    autopilotKraMaxPages: autopilotKraMaxPages
    autopilotKraCandidatesPerPage: autopilotKraCandidatesPerPage
    autopilotMarketSweepEnabled: autopilotMarketSweepEnabled
    autopilotMarketSweepLimit: autopilotMarketSweepLimit
    autopilotMarketSweepKeywords: autopilotMarketSweepKeywords
    autopilotClassificationEnabled: autopilotClassificationEnabled
    emailDeliveryMode: emailDeliveryMode
    emailSenderName: emailSenderName
    emailSender: emailSender
    emailDefaultRecipients: emailDefaultRecipients
    smtpHost: smtpHost
    smtpPort: smtpPort
    smtpUsername: smtpUsername
    smtpPasswordSecretName: smtpPasswordSecretName
    smtpUseTls: smtpUseTls
    smtpEnabled: smtpEnabled
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
