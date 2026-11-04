# Miku Assistant - what this PC has, before installing (the first-start wizard's "Tu PC" step).
# One JSON line: graphics, CPU, RAM, free disk, microphones, internet, battery. Installs nothing.
# Windows PowerShell 5.1.

$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8

$gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object { [string]$_.Name })
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$drive = Split-Path -Qualifier $env:LOCALAPPDATA
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$drive'"
# Recording endpoints that work now (names in Spanish or English Windows)
$mics = @(Get-PnpDevice -Class AudioEndpoint -Status OK |
  Where-Object { $_.FriendlyName -match 'Micr|Mic\b|Input|Entrada' } | ForEach-Object { [string]$_.FriendlyName })
$net = $false
try {
  Invoke-WebRequest -Uri 'https://download.pytorch.org/whl/cpu/torch/' -Method Head -UseBasicParsing -TimeoutSec 8 | Out-Null
  $net = $true
} catch {}
$battery = Get-CimInstance Win32_Battery | Select-Object -First 1

$o = [ordered]@{
  gpus = $gpus
  nvidia = [bool]($gpus | Where-Object { $_ -match 'NVIDIA' })
  cpu = if ($cpu) { ([string]$cpu.Name).Trim() } else { '' }
  cores = if ($cpu) { [int]$cpu.NumberOfCores } else { 0 }
  threads = if ($cpu) { [int]$cpu.NumberOfLogicalProcessors } else { 0 }
  ram = [int64](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
  free = if ($disk) { [int64]$disk.FreeSpace } else { [int64]0 }
  drive = $drive
  mics = $mics
  internet = $net
  battery = [bool]($battery -and $battery.BatteryStatus -eq 1)  # 1: running on battery (slower CPU)
}
[Console]::Out.WriteLine(($o | ConvertTo-Json -Compress))
