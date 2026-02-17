# =============================================================================
# Computer Error & Crash Diagnostic Tool (Windows PowerShell)
# =============================================================================
# Collects system info, event logs, hardware health, and crash data, then
# generates a structured prompt you can relay to an AI assistant.
#
# Usage (run PowerShell as Administrator for full results):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\diagnose.ps1
#
# Output: diagnostic_report.txt  (in the current directory)
# =============================================================================

$ErrorActionPreference = "SilentlyContinue"
$OutputFile = Join-Path (Get-Location) "diagnostic_report.txt"
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
$Divider = "=" * 80
$SectionDiv = "-" * 80
$MaxLogEntries = 100
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")

Write-Host ""
Write-Host $Divider
Write-Host "  Computer Error & Crash Diagnostic Tool (Windows)"
Write-Host "  Running at: $Timestamp"
if ($IsAdmin) {
    Write-Host "  Mode: DEEP SCAN (running as Administrator)"
} else {
    Write-Host "  Mode: BASIC SCAN (run as Administrator for deeper analysis)"
}
Write-Host $Divider
Write-Host ""
Write-Host "  Collecting data... this may take 1-3 minutes."
Write-Host ""

function Safe-Run {
    param([string]$Label, [scriptblock]$Command)
    try {
        $result = & $Command 2>&1
        if ($result) { return $result | Out-String }
        return "[No output from: $Label]"
    } catch {
        return "[Could not collect: $Label - $($_.Exception.Message)]"
    }
}

# Start building the report
$report = New-Object System.Text.StringBuilder

[void]$report.AppendLine($Divider)
[void]$report.AppendLine("COMPUTER DIAGNOSTIC REPORT (WINDOWS)")
[void]$report.AppendLine("Generated: $Timestamp")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("")
[void]$report.AppendLine("Copy everything between the START and END markers below and paste it")
[void]$report.AppendLine("to your AI assistant for analysis.")
[void]$report.AppendLine("")
[void]$report.AppendLine("========================= START OF DIAGNOSTIC PROMPT =========================")
[void]$report.AppendLine("")
[void]$report.AppendLine("I'm experiencing frequent crashes and errors on my Windows computer. Below is an")
[void]$report.AppendLine("automated diagnostic report. Please analyze it and tell me:")
[void]$report.AppendLine("1. What is most likely causing the crashes/errors")
[void]$report.AppendLine("2. Step-by-step instructions to fix each issue")
[void]$report.AppendLine("3. Any preventive measures I should take")
[void]$report.AppendLine("4. Whether any hardware may be failing and needs replacement")

# ===================== SECTION 1: SYSTEM INFO ================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 1: SYSTEM INFORMATION")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- OS Version ---")
$os = Get-CimInstance Win32_OperatingSystem
[void]$report.AppendLine("OS: $($os.Caption) $($os.Version) Build $($os.BuildNumber)")
[void]$report.AppendLine("Architecture: $($os.OSArchitecture)")
[void]$report.AppendLine("Install Date: $($os.InstallDate)")
[void]$report.AppendLine("Last Boot: $($os.LastBootUpTime)")

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Computer Info ---")
$cs = Get-CimInstance Win32_ComputerSystem
[void]$report.AppendLine("Manufacturer: $($cs.Manufacturer)")
[void]$report.AppendLine("Model: $($cs.Model)")
[void]$report.AppendLine("Total Physical Memory: $([math]::Round($cs.TotalPhysicalMemory / 1GB, 2)) GB")
[void]$report.AppendLine("System Type: $($cs.SystemType)")

[void]$report.AppendLine("")
[void]$report.AppendLine("--- CPU ---")
$cpu = Get-CimInstance Win32_Processor
foreach ($c in $cpu) {
    [void]$report.AppendLine("  Name: $($c.Name)")
    [void]$report.AppendLine("  Cores: $($c.NumberOfCores)  Logical Processors: $($c.NumberOfLogicalProcessors)")
    [void]$report.AppendLine("  Max Clock: $($c.MaxClockSpeed) MHz  Current: $($c.CurrentClockSpeed) MHz")
    [void]$report.AppendLine("  Load: $($c.LoadPercentage)%")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- BIOS ---")
$bios = Get-CimInstance Win32_BIOS
[void]$report.AppendLine("BIOS: $($bios.Manufacturer) $($bios.SMBIOSBIOSVersion)")
[void]$report.AppendLine("Serial: $($bios.SerialNumber)")

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Uptime ---")
$uptime = (Get-Date) - $os.LastBootUpTime
[void]$report.AppendLine("System uptime: $($uptime.Days)d $($uptime.Hours)h $($uptime.Minutes)m")

# ===================== SECTION 2: DISK HEALTH ================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 2: DISK & FILESYSTEM HEALTH")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Disk Drives ---")
$disks = Get-CimInstance Win32_DiskDrive
foreach ($d in $disks) {
    [void]$report.AppendLine("  $($d.Model) | Size: $([math]::Round($d.Size / 1GB, 1)) GB | Status: $($d.Status) | Interface: $($d.InterfaceType)")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Disk Space ---")
$volumes = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"
foreach ($v in $volumes) {
    $freePercent = if ($v.Size -gt 0) { [math]::Round(($v.FreeSpace / $v.Size) * 100, 1) } else { 0 }
    [void]$report.AppendLine("  $($v.DeviceID) $([math]::Round($v.FreeSpace / 1GB, 1)) GB free / $([math]::Round($v.Size / 1GB, 1)) GB total ($freePercent% free)")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- SMART / Disk Reliability ---")
try {
    $diskHealth = Get-PhysicalDisk | Select-Object FriendlyName, MediaType, HealthStatus, OperationalStatus, Size
    foreach ($dh in $diskHealth) {
        [void]$report.AppendLine("  $($dh.FriendlyName) | Type: $($dh.MediaType) | Health: $($dh.HealthStatus) | Status: $($dh.OperationalStatus)")
    }

    $diskReliability = Get-PhysicalDisk | Get-StorageReliabilityCounter
    foreach ($dr in $diskReliability) {
        [void]$report.AppendLine("  Reliability: ReadErrors=$($dr.ReadErrorsTotal) WriteErrors=$($dr.WriteErrorsTotal) Wear=$($dr.Wear) Temperature=$($dr.Temperature)C PowerOnHours=$($dr.PowerOnHours)")
    }
} catch {
    [void]$report.AppendLine("  [Could not read disk health data — run as Administrator]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Recent Disk Errors (Event Log) ---")
try {
    $diskErrors = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='disk','ntfs','volmgr','storahci'; Level=1,2,3; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 30
    foreach ($e in $diskErrors) {
        [void]$report.AppendLine("  [$($e.TimeCreated)] Level=$($e.LevelDisplayName) ID=$($e.Id) $($e.Message.Substring(0, [Math]::Min(200, $e.Message.Length)))")
    }
} catch {
    [void]$report.AppendLine("  [No recent disk errors in event log or insufficient permissions]")
}

# ===================== SECTION 3: MEMORY =====================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 3: MEMORY")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Physical Memory ---")
$memTotal = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
$memAvail = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 2)
[void]$report.AppendLine("Total: $memTotal GB")
[void]$report.AppendLine("Available: $memAvail GB")
[void]$report.AppendLine("Usage: $([math]::Round(($memTotal - $memAvail) / $memTotal * 100, 1))%")

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Memory Modules ---")
$memModules = Get-CimInstance Win32_PhysicalMemory
foreach ($m in $memModules) {
    [void]$report.AppendLine("  $($m.BankLabel): $([math]::Round($m.Capacity / 1GB, 1)) GB | Speed: $($m.Speed) MHz | Manufacturer: $($m.Manufacturer)")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Page File ---")
$pf = Get-CimInstance Win32_PageFileUsage
foreach ($p in $pf) {
    [void]$report.AppendLine("  $($p.Name): Allocated=$($p.AllocatedBaseSize) MB  Current=$($p.CurrentUsage) MB  Peak=$($p.PeakUsage) MB")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Memory Errors (Event Log) ---")
try {
    $memErrors = Get-WinEvent -FilterHashtable @{LogName='System'; Id=@(1,17,18,19,20,47); StartTime=(Get-Date).AddDays(-30)} -MaxEvents 20
    if ($memErrors) {
        foreach ($e in $memErrors) {
            [void]$report.AppendLine("  [$($e.TimeCreated)] ID=$($e.Id) $($e.Message.Substring(0, [Math]::Min(200, $e.Message.Length)))")
        }
    } else {
        [void]$report.AppendLine("  [No memory-related errors found]")
    }
} catch {
    [void]$report.AppendLine("  [Could not query memory errors]")
}

# ===================== SECTION 4: CRASH / BSOD ===============================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 4: CRASHES, BSOD & UNEXPECTED SHUTDOWNS")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Blue Screen (BugCheck) Events ---")
try {
    $bsod = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WER-SystemErrorReporting'; StartTime=(Get-Date).AddDays(-90)} -MaxEvents 30
    if ($bsod) {
        foreach ($e in $bsod) {
            [void]$report.AppendLine("  [$($e.TimeCreated)] $($e.Message)")
        }
    } else {
        [void]$report.AppendLine("  [No BSOD events found in the last 90 days]")
    }
} catch {
    [void]$report.AppendLine("  [No BSOD events found or insufficient permissions]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- BugCheck (via WMI) ---")
try {
    $bugchecks = Get-WinEvent -FilterHashtable @{LogName='System'; Id=1001; ProviderName='Microsoft-Windows-WER-SystemErrorReporting'} -MaxEvents 10
    foreach ($b in $bugchecks) {
        [void]$report.AppendLine("  [$($b.TimeCreated)] $($b.Message.Substring(0, [Math]::Min(300, $b.Message.Length)))")
    }
} catch {
    [void]$report.AppendLine("  [No BugCheck records found]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Unexpected Shutdowns ---")
try {
    $unexpShutdown = Get-WinEvent -FilterHashtable @{LogName='System'; Id=6008; StartTime=(Get-Date).AddDays(-90)} -MaxEvents 20
    if ($unexpShutdown) {
        [void]$report.AppendLine("  Found $($unexpShutdown.Count) unexpected shutdown(s):")
        foreach ($e in $unexpShutdown) {
            [void]$report.AppendLine("  [$($e.TimeCreated)] $($e.Message)")
        }
    } else {
        [void]$report.AppendLine("  [No unexpected shutdowns in the last 90 days]")
    }
} catch {
    [void]$report.AppendLine("  [No unexpected shutdown events found]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Application Crashes ---")
try {
    $appCrashes = Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; ProviderName='Application Error'; StartTime=(Get-Date).AddDays(-30)} -MaxEvents 30
    if ($appCrashes) {
        [void]$report.AppendLine("  Found $($appCrashes.Count) application crash(es):")
        foreach ($e in $appCrashes) {
            $msg = $e.Message
            if ($msg.Length -gt 300) { $msg = $msg.Substring(0, 300) + "..." }
            [void]$report.AppendLine("  [$($e.TimeCreated)] $msg")
        }
    } else {
        [void]$report.AppendLine("  [No application crashes in the last 30 days]")
    }
} catch {
    [void]$report.AppendLine("  [Could not query application crash events]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Application Hangs ---")
try {
    $appHangs = Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1002; ProviderName='Application Hang'; StartTime=(Get-Date).AddDays(-30)} -MaxEvents 20
    if ($appHangs) {
        [void]$report.AppendLine("  Found $($appHangs.Count) application hang(s):")
        foreach ($e in $appHangs) {
            $msg = $e.Message
            if ($msg.Length -gt 300) { $msg = $msg.Substring(0, 300) + "..." }
            [void]$report.AppendLine("  [$($e.TimeCreated)] $msg")
        }
    } else {
        [void]$report.AppendLine("  [No application hangs in the last 30 days]")
    }
} catch {
    [void]$report.AppendLine("  [Could not query application hang events]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Minidump Files ---")
$dumpPath = "$env:SystemRoot\Minidump"
if (Test-Path $dumpPath) {
    $dumps = Get-ChildItem $dumpPath -File | Sort-Object LastWriteTime -Descending | Select-Object -First 10
    if ($dumps) {
        foreach ($d in $dumps) {
            [void]$report.AppendLine("  $($d.Name)  Size: $([math]::Round($d.Length / 1KB, 1)) KB  Date: $($d.LastWriteTime)")
        }
    } else {
        [void]$report.AppendLine("  [Minidump directory exists but is empty]")
    }
} else {
    [void]$report.AppendLine("  [No minidump directory found]")
}

# ===================== SECTION 5: EVENT LOG ERRORS ===========================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 5: RECENT CRITICAL & ERROR EVENTS")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- System Log (Critical + Error, last 7 days) ---")
try {
    $sysErrors = Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2; StartTime=(Get-Date).AddDays(-7)} -MaxEvents $MaxLogEntries
    if ($sysErrors) {
        [void]$report.AppendLine("  Found $($sysErrors.Count) critical/error event(s):")
        foreach ($e in $sysErrors) {
            $msg = $e.Message
            if ($msg -and $msg.Length -gt 250) { $msg = $msg.Substring(0, 250) + "..." }
            [void]$report.AppendLine("  [$($e.TimeCreated)] Source=$($e.ProviderName) ID=$($e.Id) $msg")
        }
    } else {
        [void]$report.AppendLine("  [No critical/error events in System log]")
    }
} catch {
    [void]$report.AppendLine("  [Could not read System event log]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Application Log (Critical + Error, last 7 days) ---")
try {
    $appErrors = Get-WinEvent -FilterHashtable @{LogName='Application'; Level=1,2; StartTime=(Get-Date).AddDays(-7)} -MaxEvents $MaxLogEntries
    if ($appErrors) {
        [void]$report.AppendLine("  Found $($appErrors.Count) critical/error event(s):")
        foreach ($e in $appErrors) {
            $msg = $e.Message
            if ($msg -and $msg.Length -gt 250) { $msg = $msg.Substring(0, 250) + "..." }
            [void]$report.AppendLine("  [$($e.TimeCreated)] Source=$($e.ProviderName) ID=$($e.Id) $msg")
        }
    } else {
        [void]$report.AppendLine("  [No critical/error events in Application log]")
    }
} catch {
    [void]$report.AppendLine("  [Could not read Application event log]")
}

# ===================== SECTION 6: DRIVERS ====================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 6: DRIVERS")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Problem Devices ---")
try {
    $problemDevices = Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 }
    if ($problemDevices) {
        foreach ($pd in $problemDevices) {
            [void]$report.AppendLine("  $($pd.Name) | Status: Error code $($pd.ConfigManagerErrorCode) | DeviceID: $($pd.DeviceID)")
        }
    } else {
        [void]$report.AppendLine("  [All devices report OK]")
    }
} catch {
    [void]$report.AppendLine("  [Could not query device status]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Third-Party Kernel Drivers ---")
try {
    $drivers = Get-CimInstance Win32_SystemDriver | Where-Object { $_.PathName -and $_.PathName -notlike '*\windows\*' } | Select-Object Name, DisplayName, State, PathName -First 30
    if ($drivers) {
        foreach ($dr in $drivers) {
            [void]$report.AppendLine("  $($dr.Name) ($($dr.DisplayName)) | State: $($dr.State) | Path: $($dr.PathName)")
        }
    } else {
        [void]$report.AppendLine("  [No third-party kernel drivers detected]")
    }
} catch {
    [void]$report.AppendLine("  [Could not enumerate drivers]")
}

# ===================== SECTION 7: GPU ========================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 7: GPU")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Video Controllers ---")
$gpus = Get-CimInstance Win32_VideoController
foreach ($g in $gpus) {
    [void]$report.AppendLine("  $($g.Name) | Driver: $($g.DriverVersion) | Date: $($g.DriverDate) | Status: $($g.Status) | VRAM: $([math]::Round($g.AdapterRAM / 1GB, 1)) GB")
}

# ===================== SECTION 8: NETWORK ====================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 8: NETWORK")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Network Adapters ---")
try {
    $adapters = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' }
    foreach ($a in $adapters) {
        [void]$report.AppendLine("  $($a.Name) | $($a.InterfaceDescription) | Speed: $($a.LinkSpeed) | Status: $($a.Status)")
    }
} catch {
    [void]$report.AppendLine("  [Could not enumerate network adapters]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- DNS Test ---")
try {
    $dns = Resolve-DnsName google.com -Type A -ErrorAction Stop | Select-Object -First 1
    [void]$report.AppendLine("  DNS resolution OK: google.com -> $($dns.IPAddress)")
} catch {
    [void]$report.AppendLine("  [DNS resolution failed: $($_.Exception.Message)]")
}

# ===================== SECTION 9: BATTERY ====================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 9: BATTERY & POWER")
[void]$report.AppendLine($Divider)

try {
    $bat = Get-CimInstance Win32_Battery
    if ($bat) {
        foreach ($b in $bat) {
            [void]$report.AppendLine("  Battery: $($b.Name)")
            [void]$report.AppendLine("  Status: $($b.BatteryStatus) | Charge: $($b.EstimatedChargeRemaining)%")
            [void]$report.AppendLine("  Chemistry: $($b.Chemistry) | Design Voltage: $($b.DesignVoltage) mV")
        }
    } else {
        [void]$report.AppendLine("  [No battery detected — desktop system]")
    }
} catch {
    [void]$report.AppendLine("  [Could not read battery info]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Power Plan ---")
try {
    $plan = powercfg /getactivescheme 2>&1
    [void]$report.AppendLine("  $plan")
} catch {
    [void]$report.AppendLine("  [Could not read power plan]")
}

# ===================== SECTION 10: STARTUP & SERVICES ========================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 10: STARTUP & SERVICES")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Failed/Stopped Auto-Start Services ---")
try {
    $failedSvc = Get-Service | Where-Object { $_.StartType -eq 'Automatic' -and $_.Status -ne 'Running' } | Select-Object Name, DisplayName, Status -First 20
    if ($failedSvc) {
        foreach ($s in $failedSvc) {
            [void]$report.AppendLine("  $($s.Name) ($($s.DisplayName)) - Status: $($s.Status)")
        }
    } else {
        [void]$report.AppendLine("  [All auto-start services are running]")
    }
} catch {
    [void]$report.AppendLine("  [Could not query services]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Startup Programs ---")
try {
    $startup = Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location -First 20
    foreach ($su in $startup) {
        [void]$report.AppendLine("  $($su.Name) | $($su.Command) | $($su.Location)")
    }
} catch {
    [void]$report.AppendLine("  [Could not read startup programs]")
}

# ===================== SECTION 11: WINDOWS UPDATE ============================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 11: WINDOWS UPDATE")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Recent Updates ---")
try {
    $updates = Get-HotFix | Sort-Object InstalledOn -Descending -ErrorAction SilentlyContinue | Select-Object -First 15
    foreach ($u in $updates) {
        [void]$report.AppendLine("  $($u.HotFixID) | $($u.Description) | Installed: $($u.InstalledOn)")
    }
} catch {
    [void]$report.AppendLine("  [Could not query update history]")
}

# ===================== SECTION 12: TOP PROCESSES =============================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 12: TOP PROCESSES")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Top CPU Consumers ---")
$topCpu = Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name, Id, CPU, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB,1)}}
foreach ($p in $topCpu) {
    [void]$report.AppendLine("  $($p.Name) (PID $($p.Id)) | CPU: $([math]::Round($p.CPU, 1))s | Mem: $($p.MemMB) MB")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Top Memory Consumers ---")
$topMem = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name, Id, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB,1)}}
foreach ($p in $topMem) {
    [void]$report.AppendLine("  $($p.Name) (PID $($p.Id)) | Mem: $($p.MemMB) MB")
}

# ===================== SECTION 13: SFC / DISM ================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("SECTION 13: SYSTEM FILE INTEGRITY")
[void]$report.AppendLine($Divider)

[void]$report.AppendLine("")
[void]$report.AppendLine("--- SFC Log (last check) ---")
$sfcLog = "$env:SystemRoot\Logs\CBS\CBS.log"
if (Test-Path $sfcLog) {
    try {
        $sfcCorrupt = Get-Content $sfcLog -Tail 200 | Select-String -Pattern "corrupt|Cannot repair|failed" | Select-Object -Last 20
        if ($sfcCorrupt) {
            foreach ($line in $sfcCorrupt) {
                [void]$report.AppendLine("  $($line.Line.Trim())")
            }
        } else {
            [void]$report.AppendLine("  [No corruption entries found in recent CBS log]")
        }
    } catch {
        [void]$report.AppendLine("  [Could not read CBS log]")
    }
} else {
    [void]$report.AppendLine("  [CBS log not found — run 'sfc /scannow' as admin to generate]")
}

[void]$report.AppendLine("")
[void]$report.AppendLine("--- Windows Reliability (last 20 events) ---")
try {
    $reliability = Get-CimInstance Win32_ReliabilityRecords | Select-Object -First 20 TimeGenerated, SourceName, EventIdentifier, Message
    foreach ($r in $reliability) {
        $msg = if ($r.Message -and $r.Message.Length -gt 200) { $r.Message.Substring(0, 200) + "..." } else { $r.Message }
        [void]$report.AppendLine("  [$($r.TimeGenerated)] $($r.SourceName) (ID $($r.EventIdentifier)): $msg")
    }
} catch {
    [void]$report.AppendLine("  [Could not read reliability records]")
}

# ===================== END OF REPORT =========================================
[void]$report.AppendLine("")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("END OF DIAGNOSTIC DATA")
[void]$report.AppendLine($Divider)
[void]$report.AppendLine("")
[void]$report.AppendLine("Please analyze all sections above. Focus especially on:")
[void]$report.AppendLine("- BSOD/BugCheck events and the faulting drivers or modules")
[void]$report.AppendLine("- Repeated errors or patterns in the event logs")
[void]$report.AppendLine("- Any hardware issues (disk SMART failures, memory errors, overheating)")
[void]$report.AppendLine("- Application crashes and which programs are failing")
[void]$report.AppendLine("- Driver problems or devices with error codes")
[void]$report.AppendLine("- Failed services that might cause instability")
[void]$report.AppendLine("- System file corruption detected by SFC/CBS")
[void]$report.AppendLine("- Recently installed updates that might have introduced regressions")
[void]$report.AppendLine("")
[void]$report.AppendLine("Provide your analysis as:")
[void]$report.AppendLine("1. ROOT CAUSE ANALYSIS - what is most likely causing the crashes")
[void]$report.AppendLine("2. IMMEDIATE FIXES - step-by-step commands/actions to fix the most critical issues")
[void]$report.AppendLine("3. PREVENTIVE MEASURES - what to do to stop this from happening again")
[void]$report.AppendLine("4. HARDWARE ASSESSMENT - whether any hardware may need replacement")
[void]$report.AppendLine("")
[void]$report.AppendLine("========================== END OF DIAGNOSTIC PROMPT ==========================")

# Write report to file
$report.ToString() | Out-File -FilePath $OutputFile -Encoding UTF8

# Summary
Write-Host ""
Write-Host "  Diagnostic complete!"
Write-Host ""
Write-Host "  Report saved to: $OutputFile"
Write-Host "  Report size: $([math]::Round((Get-Item $OutputFile).Length / 1KB, 1)) KB"
Write-Host ""
Write-Host "  NEXT STEPS:"
Write-Host "  1. Open $OutputFile in a text editor (Notepad, VS Code, etc.)"
Write-Host "  2. Copy the entire contents (Ctrl+A, Ctrl+C)"
Write-Host "  3. Paste it into a new conversation with your AI assistant"
Write-Host "  4. The AI will analyze the data and provide specific fixes"
Write-Host ""
Write-Host $Divider
