# 远端真测 v4 部署: login + BO endpoints
$ErrorActionPreference = "Continue"

$loginBody = '{"username":"admin","password":"admin123"}'
try {
    $login = Invoke-WebRequest -Uri "http://172.20.59.7:5001/api/v1/auth/login" `
        -Method POST -ContentType "application/json" -Body $loginBody -UseBasicParsing
    Write-Host "login STATUS:" $login.StatusCode
    $data = $login.Content | ConvertFrom-Json
    $token = $data.data.token
    Write-Host "TOKEN len:" $token.Length
} catch {
    Write-Host "login FAILED:" $_.Exception.Response.StatusCode.value__
    Write-Host "body:" $_.Exception.Response
    exit 1
}

Write-Host "--- TEST 1: bo/product (with token) ---"
try {
    $r = Invoke-WebRequest -Uri "http://172.20.59.7:5001/api/v2/bo/product?page_size=10" `
        -Headers @{Authorization="Bearer $token"} -UseBasicParsing
    Write-Host "bo/product STATUS:" $r.StatusCode
    Write-Host "body (200 chars):" $r.Content.Substring(0, [Math]::Min(200, $r.Content.Length))
} catch {
    Write-Host "bo/product STATUS:" $_.Exception.Response.StatusCode.value__
    Write-Host "body:" $_.Exception.Response
}

Write-Host "--- TEST 2: menu-permission/visible (with token) ---"
try {
    $r = Invoke-WebRequest -Uri "http://172.20.59.7:5001/api/v1/menu-permission/visible" `
        -Headers @{Authorization="Bearer $token"} -UseBasicParsing
    Write-Host "menu-perm STATUS:" $r.StatusCode
} catch {
    Write-Host "menu-perm STATUS:" $_.Exception.Response.StatusCode.value__
}

Write-Host "--- TEST 3: users/me (with token) ---"
try {
    $r = Invoke-WebRequest -Uri "http://172.20.59.7:5001/api/v1/users/me" `
        -Headers @{Authorization="Bearer $token"} -UseBasicParsing
    Write-Host "users/me STATUS:" $r.StatusCode
} catch {
    Write-Host "users/me STATUS:" $_.Exception.Response.StatusCode.value__
}

Write-Host "--- TEST 4: through unified 8081 (no token) ---"
try {
    # unified 8081: 通过 Playwright 之前的验证, 它会自动注入 token
    $r = Invoke-WebRequest -Uri "http://172.20.59.7:8081/api/v1/enum-types" -UseBasicParsing
    Write-Host "8081 enum-types STATUS:" $r.StatusCode
} catch {
    Write-Host "8081 enum-types STATUS:" $_.Exception.Response.StatusCode.value__
}
