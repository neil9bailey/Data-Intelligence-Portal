targetScope = 'resourceGroup'

@description('Existing Key Vault name in this resource group.')
param keyVaultName string

@description('Principal ID to grant Key Vault Secrets User access.')
param principalId string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource keyVaultSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, principalId, 'dip-kv-secrets-user')
  scope: keyVault
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'
    )
  }
}

output roleAssignmentId string = keyVaultSecretsUserRole.id
