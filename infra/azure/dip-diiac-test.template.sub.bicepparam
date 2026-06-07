using './main.sub.bicep'

// DIIAC migration scaffold. Copy this file to infra/azure/generated/ or generate
// an environment-specific file with scripts/azure/new-customer-deployment.ps1.
// Do not deploy until the target Key Vault choice and DNS cutover window are approved.

param resourceGroupName = 'RG_DIP_DIIAC_TEST'
param resourceGroupLocation = 'uksouth'
param deployApps = false

param containerRegistryName = 'acrdipdiiactest'
param managedIdentityName = 'id-dip-diiac-test'
param logAnalyticsWorkspaceName = 'law-dip-diiac-test'
param storageAccountName = 'stdipdiiactest'
param containerAppsEnvironmentName = 'acae-dip-diiac-test'
param containerAppName = 'ca-dip-diiac-test'

// Replace with an approved existing DIIAC Key Vault before deploying.
param sharedKeyVaultName = 'REPLACE_WITH_EXISTING_DIIAC_KEY_VAULT'
param sharedKeyVaultResourceGroupName = 'REPLACE_WITH_KEY_VAULT_RESOURCE_GROUP'
param sharedKeyVaultSubscriptionId = '9ae9da49-de67-443b-af55-ce9db33ed8f4'
param publicDomain = 'cof.diiac.io'
param dnsSubdomain = 'cof'
param customDomainBindingEnabled = false
param managedCertificateName = ''

param imageRepositoryPrefix = 'dip'
param imageTag = '1.0.65-cof-value-layer'
param sqliteJournalMode = 'DELETE'
param appCpu = '2.0'
param appMemory = '4Gi'
param minReplicas = 1

param entraAuthEnabled = true
param entraTenantId = '67f8be6c-07da-4a7c-bb0a-d6bcb38cd6da'
param entraClientId = '00000000-0000-0000-0000-000000000000'
param entraClientSecretName = 'dip-diiac-test-entra-client-secret'
param entraAdminGroupId = '00000000-0000-0000-0000-000000000000'
param entraStandardGroupId = '00000000-0000-0000-0000-000000000000'
param entraAuditorGroupId = ''
param accessScopesJson = ''

param seedReferenceData = true
param seedDemoData = false
param autoApplyCustomerPacks = true

// Keep DIIAC migration deterministic until the approved API key secret exists
// in the selected DIIAC Key Vault.
param kraLlmProvider = 'disabled'
param kraModel = ''
param kraMcpMode = 'local_registry'
param kraApiKeySecretName = ''
param noticePageLimit = '10'
param noticeMaxPages = '1'
param noticeLookbackDays = '45'
param autopilotKraCustomerLimit = '3'
param autopilotKraMaxPages = '1'
param autopilotKraCandidatesPerPage = '10'
param autopilotMarketSweepEnabled = false
param autopilotMarketSweepLimit = '10'
param autopilotMarketSweepKeywords = 'cyber security,IT services,traffic management,CCTV'
param autopilotClassificationEnabled = false

param emailDeliveryMode = 'file_outbox'
param emailSenderName = 'Contracted Opportunity Finder'
param emailSender = 'no-reply@diiac.io'
param emailDefaultRecipients = ''
param smtpHost = ''
param smtpPort = '587'
param smtpUsername = ''
param smtpPasswordSecretName = ''
param smtpUseTls = true
param smtpEnabled = false
