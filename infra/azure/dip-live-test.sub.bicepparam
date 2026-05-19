using './main.sub.bicep'

param resourceGroupName = 'RG_DIP_VENDORLOGIC_TEST'
param resourceGroupLocation = 'uksouth'
param deployApps = false

param containerRegistryName = 'acrdipvltest01'
param managedIdentityName = 'id-dip-vl-test'
param logAnalyticsWorkspaceName = 'law-dip-vl-test'
param storageAccountName = 'stdipvltest01'
param containerAppsEnvironmentName = 'acae-dip-vl-test'
param containerAppName = 'ca-dip-vl-test'

param sharedKeyVaultName = 'kv-diiac-vendorlogic'
param sharedKeyVaultResourceGroupName = 'RG_ROOT'
param publicDomain = 'dip.vendorlogic.io'
param dnsSubdomain = 'dip'
param customDomainBindingEnabled = true
param managedCertificateName = 'mc-acae-dip-vl-te-dip-vendorlogic--9882'

param imageRepositoryPrefix = 'dip'
param imageTag = '1.0.35-live-test'
param sqliteJournalMode = 'DELETE'
param minReplicas = 1

param entraAuthEnabled = true
param entraTenantId = '1384b1c5-2bae-45a1-a4b4-e94e3315eb41'
param entraClientId = '00000000-0000-0000-0000-000000000000'
param entraClientSecretName = 'dip-entra-client-secret'
param entraAdminGroupId = '00000000-0000-0000-0000-000000000000'
param entraStandardGroupId = '00000000-0000-0000-0000-000000000000'
param entraAuditorGroupId = ''
param accessScopesJson = ''

param seedReferenceData = true
param seedDemoData = false
param autoApplyCustomerPacks = true

param kraLlmProvider = 'openai_direct'
param kraModel = 'gpt-5.4'
param kraMcpMode = 'local_registry'
param kraApiKeySecretName = 'diiac-openai-api-key'

param emailDeliveryMode = 'file_outbox'
param emailSenderName = 'Data Intelligence Portal'
param emailSender = 'no-reply@vendorlogic.io'
param emailDefaultRecipients = 'neil.bailey@gmail.com'
param smtpHost = ''
param smtpPort = '587'
param smtpUsername = ''
param smtpPasswordSecretName = ''
param smtpUseTls = true
param smtpEnabled = false
