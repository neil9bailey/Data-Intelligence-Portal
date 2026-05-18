targetScope = 'resourceGroup'

@description('Azure region for dedicated Data Intelligence Portal resources.')
param location string = resourceGroup().location

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
param imageTag string = '1.0.21-live-test'

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

@description('KRA LLM model name for AI-assisted summaries. Only used when KRA_LLM_PROVIDER is openai_direct and an API key secret is configured.')
param kraModel string = ''

@description('KRA MCP/agent runtime mode label shown in the UI.')
param kraMcpMode string = 'local_registry'

@description('Key Vault secret name containing the KRA/OpenAI API key. Leave blank to run KRA without AI-assisted summaries.')
param kraApiKeySecretName string = ''

@description('Default email delivery mode for the demo. Use file_outbox until an approved SMTP sender is configured.')
param emailDeliveryMode string = 'file_outbox'

@description('Default sender display name used by the report email workflow.')
param emailSenderName string = 'Data Intelligence Portal'

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

@description('Key Vault secret name containing the SMTP password/API key. Leave blank for file-outbox demo mode.')
param smtpPasswordSecretName string = ''

@description('Whether SMTP should use STARTTLS.')
param smtpUseTls bool = true

@description('Whether SMTP sending is enabled. Keep false unless SMTP credentials are configured and approved.')
param smtpEnabled bool = false

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: managedIdentityName
  location: location
}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 90
  }
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: containerRegistryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    defaultToOAuthAuthentication: false
    supportsHttpsTrafficOnly: true
  }
}

resource storageFileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource dataFileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: storageFileService
  name: 'dip-data'
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
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

resource dataStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerAppsEnvironment
  name: 'dip-data-storage'
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: dataFileShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource sharedKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: sharedKeyVaultName
  scope: resourceGroup(sharedKeyVaultSubscriptionId, sharedKeyVaultResourceGroupName)
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, managedIdentity.id, 'dip-acrpull')
  scope: containerRegistry
  properties: {
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
  }
}

var secretBaseUrl = '${sharedKeyVault.properties.vaultUri}secrets'
var entraIssuer = '${environment().authentication.loginEndpoint}${entraTenantId}/v2.0'
var allowedGroups = [
  entraAdminGroupId
  entraStandardGroupId
]
var appSecrets = concat(
  entraAuthEnabled
    ? [
        {
          name: entraClientSecretName
          keyVaultUrl: '${secretBaseUrl}/${entraClientSecretName}'
          identity: managedIdentity.id
        }
      ]
    : [],
  !empty(kraApiKeySecretName)
    ? [
        {
          name: 'kra-api-key'
          keyVaultUrl: '${secretBaseUrl}/${kraApiKeySecretName}'
          identity: managedIdentity.id
        }
      ]
    : [],
  !empty(smtpPasswordSecretName)
    ? [
        {
          name: 'dip-smtp-password'
          keyVaultUrl: '${secretBaseUrl}/${smtpPasswordSecretName}'
          identity: managedIdentity.id
        }
      ]
    : []
)
var appEnvironment = concat(
  [
    {
      name: 'APP_NAME'
      value: 'Data Intelligence Portal'
    }
    {
      name: 'DATABASE_URL'
      value: 'sqlite:////tmp/dip/data-intelligence-portal.sqlite'
    }
    {
      name: 'SQLITE_JOURNAL_MODE'
      value: sqliteJournalMode
    }
    {
      name: 'SQLITE_PERSISTENT_COPY_PATH'
      value: '/app/data/data-intelligence-portal.sqlite'
    }
    {
      name: 'DIP_OUTBOX_DIR'
      value: '/app/data/outbox'
    }
    {
      name: 'DIP_PUBLIC_DOMAIN'
      value: publicDomain
    }
    {
      name: 'DIP_REMOTE_HEALTH_URL'
      value: 'https://${publicDomain}/healthz'
    }
    {
      name: 'DIP_DEPLOYMENT_LABEL'
      value: 'azure-live-test'
    }
    {
      name: 'SEED_REFERENCE_DATA'
      value: seedReferenceData ? 'true' : 'false'
    }
    {
      name: 'SEED_DEMO_DATA'
      value: seedDemoData ? 'true' : 'false'
    }
    {
      name: 'AUTO_APPLY_CUSTOMER_PACKS'
      value: autoApplyCustomerPacks ? 'true' : 'false'
    }
    {
      name: 'ENTRA_AUTH_ENABLED'
      value: entraAuthEnabled ? 'true' : 'false'
    }
    {
      name: 'ENTRA_ADMIN_GROUP_ID'
      value: entraAdminGroupId
    }
    {
      name: 'ENTRA_STANDARD_GROUP_ID'
      value: entraStandardGroupId
    }
    {
      name: 'KRA_LLM_PROVIDER'
      value: kraLlmProvider
    }
    {
      name: 'KRA_MODEL'
      value: kraModel
    }
    {
      name: 'KRA_MCP_MODE'
      value: kraMcpMode
    }
    {
      name: 'DIP_EMAIL_DELIVERY_MODE'
      value: emailDeliveryMode
    }
    {
      name: 'DIP_EMAIL_SENDER_NAME'
      value: emailSenderName
    }
    {
      name: 'DIP_EMAIL_SENDER'
      value: emailSender
    }
    {
      name: 'DIP_EMAIL_DEFAULT_RECIPIENTS'
      value: emailDefaultRecipients
    }
    {
      name: 'DIP_SMTP_HOST'
      value: smtpHost
    }
    {
      name: 'DIP_SMTP_PORT'
      value: smtpPort
    }
    {
      name: 'DIP_SMTP_USERNAME'
      value: smtpUsername
    }
    {
      name: 'DIP_SMTP_USE_TLS'
      value: smtpUseTls ? 'true' : 'false'
    }
    {
      name: 'DIP_SMTP_ENABLED'
      value: smtpEnabled ? 'true' : 'false'
    }
  ],
  !empty(kraApiKeySecretName)
    ? [
        {
          name: 'KRA_API_KEY'
          secretRef: 'kra-api-key'
        }
        {
          name: 'OPENAI_API_KEY'
          secretRef: 'kra-api-key'
        }
        {
          name: 'OPENAI_MODEL'
          value: kraModel
        }
      ]
    : [],
  !empty(smtpPasswordSecretName)
    ? [
        {
          name: 'DIP_SMTP_PASSWORD'
          secretRef: 'dip-smtp-password'
        }
      ]
    : []
)

resource existingManagedCertificate 'Microsoft.App/managedEnvironments/managedCertificates@2024-03-01' existing = if (deployApps && customDomainBindingEnabled) {
  parent: containerAppsEnvironment
  name: managedCertificateName
}

resource portalApp 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        allowInsecure: false
        transport: 'auto'
        customDomains: customDomainBindingEnabled
          ? [
              {
                name: publicDomain
                bindingType: 'SniEnabled'
                certificateId: existingManagedCertificate.id
              }
            ]
          : []
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: appSecrets
    }
    template: {
      containers: [
        {
          name: 'data-intelligence-portal'
          image: '${containerRegistry.properties.loginServer}/${imageRepositoryPrefix}/app:${imageTag}'
          env: appEnvironment
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8080
              }
              initialDelaySeconds: 60
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: 8080
              }
              initialDelaySeconds: 30
              periodSeconds: 15
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
          volumeMounts: [
            {
              volumeName: 'dip-data-volume'
              mountPath: '/app/data'
            }
          ]
          resources: {
            cpu: json(appCpu)
            memory: appMemory
          }
        }
      ]
      volumes: [
        {
          name: 'dip-data-volume'
          storageType: 'AzureFile'
          storageName: dataStorage.name
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
  dependsOn: [
    acrPullRole
  ]
}

resource portalAuth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (deployApps && entraAuthEnabled) {
  parent: portalApp
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
      excludedPaths: [
        '/healthz'
      ]
    }
    httpSettings: {
      requireHttps: true
      routes: {
        apiPrefix: '/.auth'
      }
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: entraClientId
          clientSecretSettingName: entraClientSecretName
          openIdIssuer: entraIssuer
        }
        validation: {
          allowedAudiences: [
            entraClientId
            'api://${entraClientId}'
          ]
          defaultAuthorizationPolicy: {
            allowedPrincipals: {
              groups: allowedGroups
              identities: []
            }
            allowedApplications: []
          }
          jwtClaimChecks: {
            allowedGroups: allowedGroups
            allowedClientApplications: []
          }
        }
      }
    }
  }
}

output acrName string = containerRegistry.name
output acrLoginServer string = containerRegistry.properties.loginServer
output storageAccountName string = storageAccount.name
output managedIdentityId string = managedIdentity.id
output managedIdentityPrincipalId string = managedIdentity.properties.principalId
output managedEnvironmentId string = containerAppsEnvironment.id
output managedEnvironmentName string = containerAppsEnvironment.name
output managedEnvironmentDefaultDomain string = containerAppsEnvironment.properties.defaultDomain
output managedEnvironmentStaticIp string = containerAppsEnvironment.properties.staticIp
output sharedKeyVaultId string = sharedKeyVault.id
output sharedKeyVaultUri string = sharedKeyVault.properties.vaultUri
output containerAppName string = deployApps ? portalApp!.name : ''
output containerAppFqdn string = deployApps ? portalApp!.properties.configuration.ingress.fqdn : ''
output containerAppUrl string = deployApps ? 'https://${portalApp!.properties.configuration.ingress.fqdn}' : ''
output dnsCnameHost string = dnsSubdomain
output dnsCnameTarget string = deployApps ? portalApp!.properties.configuration.ingress.fqdn : ''
output dnsTxtHost string = 'asuid.${dnsSubdomain}'
output dnsTxtValue string = deployApps ? portalApp!.properties.customDomainVerificationId : ''
output customDomain string = publicDomain
