$ErrorActionPreference = 'Stop'
$artifact = (Resolve-Path -LiteralPath 'D:\projects\das\dist\v2.1.26\DASViewer-v2.1.26.exe').Path
$expected = 'D:\projects\das\dist\v2.1.26\DASViewer-v2.1.26.exe'
if ($artifact -ne $expected) { throw "Unexpected executable: $artifact" }
$before = @(Get-Process | Where-Object { $_.Path -eq $artifact } | Select-Object -ExpandProperty Id)
$env:QT_QPA_PLATFORM = 'offscreen'
$started = Start-Process -FilePath $artifact -WindowStyle Hidden -PassThru
try {
    Start-Sleep -Seconds 12
    $started.Refresh()
    if ($started.HasExited) { throw "Startup exited early with code $($started.ExitCode)" }
    $targets = @(Get-Process | Where-Object { $_.Path -eq $artifact -and $_.Id -notin $before })
    if ($targets.Count -lt 2) { throw 'The one-file application child did not remain running.' }
    "Packaged startup remained running: $($targets.Id -join ', ')"
} finally {
    $targets = @(Get-Process | Where-Object { $_.Path -eq $artifact -and $_.Id -notin $before })
    foreach ($target in $targets) {
        if ($target.Path -ne $expected) { throw "Unexpected process: $($target.Id) $($target.Path)" }
    }
    if ($targets.Count -gt 0) { Stop-Process -Id $targets.Id -ErrorAction Stop }
    'Stopped only the newly created startup-check processes.'
}
