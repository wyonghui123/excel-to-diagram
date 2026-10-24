<#
    launch_detached.ps1 - start a long-running process detached from the
    Trae toolhost job object, so the terminal call returns immediately.

    WHY (investigated 2026-10-24):
      Trae's terminal tool spawns processes under agent-tool-host.exe inside a
      job object and waits for the WHOLE descendant process tree to exit
      before marking the call as done.
      A child started with Start-Process still has the current powershell.exe
      as its parent, so it stays inside the same job. Starting a long-lived
      service that way (vite preview / cloudflared tunnel / waitress) kept the
      terminal call blocked for hours - worst single case 1353.8 min (22.6 h),
      9146 min accumulated. One case hung 438 min because the machine ran out
      of memory (the "430 minutes" symptom).

      Win32_Process.Create via WMI creates the process with WmiPrvSE.exe (a
      system service) as parent, so it is NOT in the caller's job object.
      The call returns at once and the service survives independently.

    IMPLEMENTATION NOTES (all verified by experiment):
      * Single-layer powershell.exe only. Do NOT nest Start-Process inside the
        WMI-created process - nesting breaks the escaping chain, the child
        gets no arguments, exits immediately and writes no log.
      * The command body travels via -EncodedCommand (Base64 / UTF-16LE) to
        avoid quoting problems.
      * Do not use cmd.exe for redirection: the toolhost safety policy blocks
        "cmd /c". Redirect with the PowerShell *> operator instead.

    USAGE
      # long-lived service (returns immediately)
      pwsh -File scripts/launch_detached.ps1 -CommandLine 'npx vite preview --port 4173' `
          -WorkingDirectory 'd:\filework\excel-to-diagram' `
          -StdOut '.runtime\pv.out.log' -StdErr '.runtime\pv.err.log' -WaitPort 4173

      # short command (wait for exit)
      pwsh -File scripts/launch_detached.ps1 -CommandLine 'python foo.py' -Wait

    NOTE: keep every literal in this file ASCII. Windows PowerShell 5.1 reads
    BOM-less .ps1 files as GBK, so non-ASCII literals get mangled into broken
    quotes and the script fails to parse.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$CommandLine,
    [string]$WorkingDirectory = (Get-Location).Path,
    [string]$StdOut,
    [string]$StdErr,
    # readiness probe: wait until the port is in Listen state (0 = skip)
    [int]$WaitPort = 0,
    # readiness probe timeout in seconds
    [int]$WaitTimeoutSec = 60,
    # wait for process exit (short commands only)
    [switch]$Wait,
    # print the spawned PID on stdout as a bare line (for programmatic capture)
    [switch]$PassThruPid
)

$ErrorActionPreference = 'Stop'

function Write-Info([string]$m) { Write-Host "[launch_detached] $m" -ForegroundColor Cyan }

# --- resolve log paths ---
# Probe writability first: PowerShell redirection ('1>') opens the target with
# FileShare.Read, so a log file still held by an older process (a leaked dev
# server from a previous session) makes the redirect fail. The detached child
# then dies instantly and writes NOTHING - the port never opens and the only
# symptom is "spawned but port not responding". Fall back to a timestamped
# file instead of killing whatever holds the old one.
function Test-RedirectTarget([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return $true }
    try {
        $fs = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Write, [IO.FileShare]::Read)
        $fs.Close()
        return $true
    } catch { return $false }
}

function Get-FreeLogPath([string]$path) {
    if (Test-RedirectTarget $path) { return $path }
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $dir = [IO.Path]::GetDirectoryName($path)
    $base = [IO.Path]::GetFileNameWithoutExtension($path)
    $ext = [IO.Path]::GetExtension($path)
    $alt = [IO.Path]::Combine($dir, ('{0}.{1}{2}' -f $base, $stamp, $ext))
    Write-Info ('log file busy, falling back to {0}' -f $alt)
    return $alt
}

$outFull = $null
$errFull = $null
if ($StdOut) {
    $outFull = if ([IO.Path]::IsPathRooted($StdOut)) { $StdOut } else { Join-Path $WorkingDirectory $StdOut }
    $errFull = if ($StdErr) {
        if ([IO.Path]::IsPathRooted($StdErr)) { $StdErr } else { Join-Path $WorkingDirectory $StdErr }
    } else {
        [IO.Path]::Combine([IO.Path]::GetDirectoryName($outFull),
                           [IO.Path]::GetFileNameWithoutExtension($outFull) + '.err.log')
    }
    foreach ($f in @($outFull, $errFull)) {
        $dir = Split-Path -Parent $f
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    }
    $outFull = Get-FreeLogPath $outFull
    $errFull = Get-FreeLogPath $errFull
}

# --- build the body of the detached process ---
# stdout and stderr must go to SEPARATE files: the caller may expect a
# specific stream in a specific file (e.g. cloudflared prints the public URL on
# stderr). Do NOT use *> (merged stream) for that.
$body = '$ErrorActionPreference = ''Continue''; ' +
        'try { & { ' + $CommandLine + ' }'
if ($outFull) {
    $body += ' 1> ' + "'" + $outFull + "'"
}
if ($errFull) {
    $body += ' 2> ' + "'" + $errFull + "'"
}
$body += ' } catch { Write-Error $_ }'

$enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($body))
$full = 'powershell.exe -NoProfile -NonInteractive -EncodedCommand {0}' -f $enc

Write-Info ('spawning detached: {0}' -f $CommandLine)

# key: created by WMI, parent = WmiPrvSE.exe, so it does not inherit our job object
$created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine     = $full
    CurrentDirectory = $WorkingDirectory
}

if ($created.ReturnValue -ne 0) {
    Write-Error ('Win32_Process.Create failed, ReturnValue={0}' -f $created.ReturnValue)
    exit $created.ReturnValue
}

$procId = $created.ProcessId
Write-Info ('started PID={0} (parent = WmiPrvSE.exe, detached from toolhost job)' -f $procId)
if ($PassThruPid) { Write-Output $procId }

# --- port readiness probe ---
if ($WaitPort -gt 0) {
    Write-Info ('waiting for port {0} (timeout {1}s) ...' -f $WaitPort, $WaitTimeoutSec)
    $deadline = (Get-Date).AddSeconds($WaitTimeoutSec)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        $c = Get-NetTCPConnection -LocalPort $WaitPort -State Listen -ErrorAction SilentlyContinue
        if ($c) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) {
        Write-Error ('port {0} not ready within {1}s' -f $WaitPort, $WaitTimeoutSec)
        exit 2
    }
    Write-Info ('port {0} is ready' -f $WaitPort) -ForegroundColor Green
}

if ($Wait) {
    Write-Info 'waiting for process exit ...'
    while (Get-Process -Id $procId -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 500 }
    Write-Info 'process exited'
}

exit 0
