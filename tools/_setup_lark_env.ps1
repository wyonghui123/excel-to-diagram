# Set user-level env vars (no admin required)
# Task Scheduler running as this user can read them
$appId     = 'cli_a9362787bbb8dcb5'
$appSecret = 'd176KW7qFBHsJ8Wbg9scCceuhqqAHsby'
$chatId    = 'oc_59f8af4c5cb539e4f944b78c2c8de73d'

[Environment]::SetEnvironmentVariable('LARK_APP_ID',     $appId,     'User')
[Environment]::SetEnvironmentVariable('LARK_APP_SECRET', $appSecret, 'User')
[Environment]::SetEnvironmentVariable('LARK_CHAT_ID',    $chatId,    'User')

# Verify
$checkId     = [Environment]::GetEnvironmentVariable('LARK_APP_ID',     'User')
$checkSecret = [Environment]::GetEnvironmentVariable('LARK_APP_SECRET', 'User')
$checkChat   = [Environment]::GetEnvironmentVariable('LARK_CHAT_ID',    'User')

Write-Host "[OK] LARK_APP_ID     = $checkId"
Write-Host "[OK] LARK_APP_SECRET = $($checkSecret.Substring(0,8))..."
Write-Host "[OK] LARK_CHAT_ID    = $checkChat"
Write-Host "[INFO] User-level env vars written to HKCU\Environment"
