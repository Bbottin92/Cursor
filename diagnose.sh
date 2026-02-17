#!/usr/bin/env bash
# =============================================================================
# Computer Error & Crash Diagnostic Tool (Linux / macOS)
# =============================================================================
# Collects system info, logs, hardware health, and crash data, then generates
# a structured prompt you can relay to an AI assistant for troubleshooting.
#
# Usage:
#   chmod +x diagnose.sh
#   ./diagnose.sh              # basic scan (no sudo required)
#   sudo ./diagnose.sh         # deep scan (recommended – unlocks SMART, dmesg, etc.)
#
# Output: diagnostic_report.txt  (in the current directory)
# =============================================================================

set -euo pipefail

# --------------- Configuration ---------------
MAX_LOG_LINES=150          # max lines to capture per log source
MAX_PROCESS_LINES=20       # top processes by CPU/memory
OUTPUT_FILE="diagnostic_report.txt"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S %Z')
DIVIDER="================================================================================"
SECTION_DIV="--------------------------------------------------------------------------------"

# --------------- Helpers ---------------
is_root() { [[ $EUID -eq 0 ]]; }
is_linux() { [[ "$(uname -s)" == "Linux" ]]; }
is_macos() { [[ "$(uname -s)" == "Darwin" ]]; }
cmd_exists() { command -v "$1" &>/dev/null; }
safe_run() {
    local label="$1"; shift
    local output
    if output=$("$@" 2>&1); then
        echo "$output"
    else
        echo "[Could not collect: $label — command failed or not available]"
    fi
}

truncate_output() {
    local max_lines="${1:-$MAX_LOG_LINES}"
    head -n "$max_lines"
}

# --------------- Banner ---------------
echo ""
echo "$DIVIDER"
echo "  Computer Error & Crash Diagnostic Tool"
echo "  Running at: $TIMESTAMP"
if is_root; then
    echo "  Mode: DEEP SCAN (running as root)"
else
    echo "  Mode: BASIC SCAN (run with sudo for deeper analysis)"
fi
echo "$DIVIDER"
echo ""

# --------------- Start Report ---------------
{
cat <<HEADER
$DIVIDER
COMPUTER DIAGNOSTIC REPORT
Generated: $TIMESTAMP
$DIVIDER

Copy everything between the START and END markers below and paste it
to your AI assistant for analysis.

========================= START OF DIAGNOSTIC PROMPT =========================

I'm experiencing frequent crashes and errors on my computer. Below is an
automated diagnostic report. Please analyze it and tell me:
1. What is most likely causing the crashes/errors
2. Step-by-step instructions to fix each issue
3. Any preventive measures I should take
4. Whether any hardware may be failing and needs replacement

HEADER

# ======================= SECTION 1: SYSTEM INFO ==============================
cat <<EOF

$DIVIDER
SECTION 1: SYSTEM INFORMATION
$DIVIDER
EOF

echo "--- OS & Kernel ---"
if is_macos; then
    echo "Platform: macOS"
    safe_run "sw_vers" sw_vers
    echo "Kernel: $(uname -srm)"
elif is_linux; then
    echo "Platform: Linux"
    if [[ -f /etc/os-release ]]; then
        safe_run "os-release" cat /etc/os-release
    fi
    echo "Kernel: $(uname -srm)"
fi

echo ""
echo "--- Hostname ---"
hostname 2>/dev/null || echo "[unknown]"

echo ""
echo "--- Uptime ---"
uptime 2>/dev/null || echo "[unknown]"

echo ""
echo "--- Hardware Overview ---"
if is_macos; then
    safe_run "system_profiler" system_profiler SPHardwareDataType 2>/dev/null
elif is_linux; then
    if cmd_exists lscpu; then
        echo "CPU:"
        lscpu | head -20
    fi
    echo ""
    if [[ -f /proc/meminfo ]]; then
        echo "Memory:"
        head -5 /proc/meminfo
    fi
    echo ""
    if cmd_exists lspci; then
        echo "Key PCI devices:"
        safe_run "lspci" lspci 2>/dev/null | truncate_output 30
    fi
fi

echo ""
echo "--- Boot Mode ---"
if is_linux; then
    if [[ -d /sys/firmware/efi ]]; then
        echo "UEFI boot"
    else
        echo "Legacy/BIOS boot"
    fi
elif is_macos; then
    echo "macOS (EFI)"
fi


# ======================= SECTION 2: DISK HEALTH ==============================
cat <<EOF

$DIVIDER
SECTION 2: DISK & FILESYSTEM HEALTH
$DIVIDER
EOF

echo "--- Disk Space ---"
df -h 2>/dev/null | truncate_output 30

echo ""
echo "--- Filesystem Mounts ---"
mount 2>/dev/null | truncate_output 40

echo ""
echo "--- SMART Disk Health ---"
if cmd_exists smartctl; then
    for disk in /dev/sd? /dev/nvme?n?; do
        if [[ -b "$disk" ]]; then
            echo ""
            echo ">> $disk"
            if is_root; then
                safe_run "smartctl $disk" smartctl -a "$disk" 2>/dev/null | truncate_output 60
            else
                echo "[Run with sudo to read SMART data for $disk]"
            fi
        fi
    done
elif is_macos; then
    echo "diskutil info / :"
    safe_run "diskutil" diskutil info / 2>/dev/null | truncate_output 30
else
    echo "[smartctl not installed — install smartmontools for disk health data]"
fi

echo ""
echo "--- Recent Filesystem Errors (dmesg) ---"
if is_linux; then
    if is_root || [[ -r /dev/kmsg ]]; then
        safe_run "dmesg fs errors" dmesg 2>/dev/null | grep -iE 'error|fail|corrupt|readonly|ext4|btrfs|xfs|ntfs|i/o' | tail -n "$MAX_LOG_LINES"
    else
        echo "[Run with sudo for dmesg access]"
    fi
elif is_macos; then
    safe_run "disk errors" log show --predicate 'subsystem == "com.apple.DiskArbitration"' --last 1d --style compact 2>/dev/null | tail -n 30
fi


# ======================= SECTION 3: MEMORY ====================================
cat <<EOF

$DIVIDER
SECTION 3: MEMORY
$DIVIDER
EOF

echo "--- Memory Usage ---"
free -h 2>/dev/null || vm_stat 2>/dev/null || echo "[unknown]"

echo ""
echo "--- Swap Usage ---"
if is_linux; then
    swapon --show 2>/dev/null || echo "[no swap or unknown]"
elif is_macos; then
    sysctl vm.swapusage 2>/dev/null || echo "[unknown]"
fi

echo ""
echo "--- OOM Killer Events (Linux) ---"
if is_linux; then
    if is_root || [[ -r /dev/kmsg ]]; then
        oom_lines=$(dmesg 2>/dev/null | grep -ic "oom\|out of memory" || true)
        echo "OOM events in kernel ring buffer: $oom_lines"
        if [[ "$oom_lines" -gt 0 ]]; then
            dmesg 2>/dev/null | grep -i "oom\|out of memory" | tail -n 30
        fi
    else
        if cmd_exists journalctl; then
            oom_lines=$(journalctl -k --no-pager 2>/dev/null | grep -ic "oom\|out of memory" || true)
            echo "OOM events in journal: $oom_lines"
            if [[ "$oom_lines" -gt 0 ]]; then
                journalctl -k --no-pager 2>/dev/null | grep -i "oom\|out of memory" | tail -n 30
            fi
        fi
    fi
fi

echo ""
echo "--- Memory Hardware Errors ---"
if is_linux && cmd_exists edac-util; then
    safe_run "edac" edac-util -s 2>/dev/null
elif is_linux && [[ -d /sys/devices/system/edac/mc ]]; then
    echo "EDAC corrected errors:"
    for mc in /sys/devices/system/edac/mc/mc*; do
        if [[ -f "$mc/ce_count" ]]; then
            echo "  $(basename "$mc"): corrected=$(cat "$mc/ce_count") uncorrected=$(cat "$mc/ue_count" 2>/dev/null || echo '?')"
        fi
    done
else
    echo "[No EDAC/memory error data available]"
fi


# ======================= SECTION 4: CPU & THERMALS ============================
cat <<EOF

$DIVIDER
SECTION 4: CPU & THERMAL
$DIVIDER
EOF

echo "--- CPU Info ---"
if is_linux; then
    grep -m1 'model name' /proc/cpuinfo 2>/dev/null || echo "[unknown CPU]"
    echo "Cores: $(nproc 2>/dev/null || echo '?')"
    echo ""
    echo "CPU frequency:"
    if [[ -f /proc/cpuinfo ]]; then
        grep 'cpu MHz' /proc/cpuinfo 2>/dev/null | head -4
    fi
elif is_macos; then
    sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "[unknown CPU]"
    echo "Cores: $(sysctl -n hw.ncpu 2>/dev/null || echo '?')"
fi

echo ""
echo "--- CPU Load ---"
uptime
echo ""
echo "--- Top CPU Consumers ---"
if is_linux; then
    ps aux --sort=-%cpu 2>/dev/null | head -n "$MAX_PROCESS_LINES"
elif is_macos; then
    ps aux -r 2>/dev/null | head -n "$MAX_PROCESS_LINES"
fi

echo ""
echo "--- Temperatures ---"
if cmd_exists sensors; then
    safe_run "sensors" sensors 2>/dev/null
elif is_linux && [[ -d /sys/class/thermal ]]; then
    for tz in /sys/class/thermal/thermal_zone*; do
        if [[ -f "$tz/type" && -f "$tz/temp" ]]; then
            type=$(cat "$tz/type")
            temp=$(cat "$tz/temp")
            echo "  $type: $((temp / 1000))°C"
        fi
    done
elif is_macos && cmd_exists osx-cpu-temp; then
    osx-cpu-temp 2>/dev/null
else
    echo "[No temperature sensors detected — install lm-sensors on Linux]"
fi

echo ""
echo "--- Thermal Throttling (Linux) ---"
if is_linux; then
    if is_root || [[ -r /dev/kmsg ]]; then
        throttle_count=$(dmesg 2>/dev/null | grep -ic "throttl" || true)
        echo "Throttling events in dmesg: $throttle_count"
        if [[ "$throttle_count" -gt 0 ]]; then
            dmesg 2>/dev/null | grep -i "throttl" | tail -n 20
        fi
    else
        echo "[Run with sudo for throttle detection]"
    fi
fi


# ======================= SECTION 5: GPU =======================================
cat <<EOF

$DIVIDER
SECTION 5: GPU
$DIVIDER
EOF

if cmd_exists nvidia-smi; then
    echo "--- NVIDIA GPU Status ---"
    safe_run "nvidia-smi" nvidia-smi 2>/dev/null
elif cmd_exists lspci; then
    echo "--- GPU Devices ---"
    lspci 2>/dev/null | grep -iE 'vga|3d|display' || echo "[none found]"
fi

if is_linux; then
    echo ""
    echo "--- GPU Errors in Logs ---"
    if is_root || [[ -r /dev/kmsg ]]; then
        gpu_errors=$(dmesg 2>/dev/null | grep -iE 'gpu|drm|nvidia|amdgpu|radeon|i915' | grep -iE 'error|fail|fault|hang|timeout' | tail -n 30)
        if [[ -n "$gpu_errors" ]]; then
            echo "$gpu_errors"
        else
            echo "[No GPU errors found in dmesg]"
        fi
    else
        echo "[Run with sudo for GPU error detection]"
    fi
fi


# ======================= SECTION 6: SYSTEM LOGS ==============================
cat <<EOF

$DIVIDER
SECTION 6: SYSTEM LOGS & CRASH DATA
$DIVIDER
EOF

echo "--- Recent Critical/Error Log Entries ---"
if is_linux && cmd_exists journalctl; then
    echo ""
    echo ">> journalctl priority 0-3 (emerg/alert/crit/err) — last 3 boots:"
    safe_run "journalctl errors" journalctl -p 0..3 -b -0 --no-pager 2>/dev/null | tail -n "$MAX_LOG_LINES"

    echo ""
    echo ">> Previous boot errors (if available):"
    safe_run "journalctl prev boot" journalctl -p 0..3 -b -1 --no-pager 2>/dev/null | tail -n 80

    echo ""
    echo ">> Boot before that (if available):"
    safe_run "journalctl prev-prev boot" journalctl -p 0..3 -b -2 --no-pager 2>/dev/null | tail -n 40

elif is_macos; then
    echo ""
    echo ">> macOS system log errors (last 24h):"
    safe_run "log show errors" log show --predicate 'messageType == error' --last 24h --style compact 2>/dev/null | tail -n "$MAX_LOG_LINES"
fi

echo ""
echo "--- Kernel Panics / Crash Reports ---"
if is_linux; then
    echo ">> Checking for kernel panics in logs:"
    if cmd_exists journalctl; then
        panic_lines=$(journalctl -k --no-pager 2>/dev/null | grep -ic "panic\|oops\|BUG:" || true)
        echo "Kernel panic/oops/BUG events found: $panic_lines"
        if [[ "$panic_lines" -gt 0 ]]; then
            journalctl -k --no-pager 2>/dev/null | grep -iB2 -A5 "panic\|oops\|BUG:" | tail -n 60
        fi
    fi
    echo ""
    echo ">> Checking for crash dumps:"
    if [[ -d /var/crash ]]; then
        echo "Files in /var/crash:"
        ls -lah /var/crash/ 2>/dev/null || echo "  [empty or inaccessible]"
    fi
    if cmd_exists coredumpctl; then
        echo ""
        echo ">> Recent coredumps:"
        safe_run "coredumpctl" coredumpctl list --no-pager 2>/dev/null | tail -n 30
    fi
elif is_macos; then
    echo ">> Recent panic reports:"
    if [[ -d /Library/Logs/DiagnosticReports ]]; then
        ls -lt /Library/Logs/DiagnosticReports/*.panic 2>/dev/null | head -5
        latest_panic=$(ls -t /Library/Logs/DiagnosticReports/*.panic 2>/dev/null | head -1)
        if [[ -n "$latest_panic" ]]; then
            echo ""
            echo ">> Latest panic report ($latest_panic):"
            head -n 80 "$latest_panic"
        fi
    fi
    echo ""
    echo ">> Recent crash reports:"
    ls -lt ~/Library/Logs/DiagnosticReports/*.crash 2>/dev/null | head -10 || echo "[none found]"
fi

echo ""
echo "--- Failed Systemd Services (Linux) ---"
if is_linux && cmd_exists systemctl; then
    safe_run "failed units" systemctl --failed --no-pager 2>/dev/null
fi

echo ""
echo "--- Recent Shutdowns / Reboots ---"
if cmd_exists last; then
    echo ">> Recent reboots:"
    last reboot 2>/dev/null | head -15
    echo ""
    echo ">> Recent shutdowns:"
    last shutdown 2>/dev/null | head -15 || last -x shutdown 2>/dev/null | head -15 || echo "[no shutdown records]"
fi

echo ""
echo "--- Unexpected Shutdowns ---"
if is_linux && cmd_exists journalctl; then
    echo ">> Checking for unclean shutdowns:"
    journalctl --list-boots --no-pager 2>/dev/null | head -20
fi


# ======================= SECTION 7: NETWORK ===================================
cat <<EOF

$DIVIDER
SECTION 7: NETWORK
$DIVIDER
EOF

echo "--- Network Interfaces ---"
if cmd_exists ip; then
    ip -br addr 2>/dev/null
elif cmd_exists ifconfig; then
    ifconfig 2>/dev/null | grep -E 'flags|inet ' | truncate_output 20
fi

echo ""
echo "--- Network Errors ---"
if cmd_exists ip; then
    echo ">> Interface statistics (errors/drops):"
    ip -s link 2>/dev/null | grep -A4 -E '^[0-9]+:' | grep -E 'errors|dropped|overrun|carrier' | head -20
elif cmd_exists netstat; then
    netstat -i 2>/dev/null | head -15
fi

echo ""
echo "--- DNS Resolution Test ---"
safe_run "dns" host google.com 2>/dev/null || safe_run "dns" nslookup google.com 2>/dev/null || echo "[DNS test failed]"


# ======================= SECTION 8: PACKAGES ==================================
cat <<EOF

$DIVIDER
SECTION 8: RECENTLY INSTALLED / UPDATED PACKAGES
$DIVIDER
EOF

if is_linux; then
    if cmd_exists dpkg; then
        echo ">> Last 30 package changes (dpkg):"
        grep -E 'install|upgrade|remove' /var/log/dpkg.log 2>/dev/null | tail -n 30 || echo "[no dpkg log]"
    fi
    if cmd_exists rpm; then
        echo ">> Last 30 package changes (rpm):"
        rpm -qa --last 2>/dev/null | head -30 || echo "[no rpm data]"
    fi
    if [[ -f /var/log/pacman.log ]]; then
        echo ">> Last 30 package changes (pacman):"
        grep -E 'installed|upgraded|removed' /var/log/pacman.log 2>/dev/null | tail -n 30
    fi
elif is_macos; then
    echo ">> Homebrew recent activity:"
    if cmd_exists brew; then
        brew list --versions 2>/dev/null | tail -n 20 || echo "[no brew data]"
    fi
fi


# ======================= SECTION 9: BATTERY (LAPTOPS) =========================
cat <<EOF

$DIVIDER
SECTION 9: BATTERY & POWER (LAPTOP)
$DIVIDER
EOF

if is_linux; then
    if [[ -d /sys/class/power_supply ]]; then
        for bat in /sys/class/power_supply/BAT*; do
            if [[ -d "$bat" ]]; then
                echo ">> $(basename "$bat"):"
                [[ -f "$bat/status" ]] && echo "  Status: $(cat "$bat/status")"
                [[ -f "$bat/capacity" ]] && echo "  Capacity: $(cat "$bat/capacity")%"
                [[ -f "$bat/cycle_count" ]] && echo "  Cycle count: $(cat "$bat/cycle_count")"
                if [[ -f "$bat/energy_full" && -f "$bat/energy_full_design" ]]; then
                    full=$(cat "$bat/energy_full")
                    design=$(cat "$bat/energy_full_design")
                    if [[ "$design" -gt 0 ]]; then
                        health=$((full * 100 / design))
                        echo "  Battery health: ${health}% of design capacity"
                    fi
                fi
            fi
        done
    else
        echo "[No battery detected — desktop or unsupported]"
    fi
elif is_macos; then
    safe_run "battery" system_profiler SPPowerDataType 2>/dev/null | head -30
fi


# ======================= SECTION 10: MISC =====================================
cat <<EOF

$DIVIDER
SECTION 10: ADDITIONAL CHECKS
$DIVIDER
EOF

echo "--- Zombie Processes ---"
if is_linux; then
    zombie_count=$(ps aux 2>/dev/null | awk '$8 ~ /Z/' | wc -l)
    echo "Zombie processes: $zombie_count"
    if [[ "$zombie_count" -gt 0 ]]; then
        ps aux 2>/dev/null | awk '$8 ~ /Z/' | head -10
    fi
fi

echo ""
echo "--- High Memory Consumers ---"
if is_linux; then
    ps aux --sort=-%mem 2>/dev/null | head -n "$MAX_PROCESS_LINES"
elif is_macos; then
    ps aux -m 2>/dev/null | head -n "$MAX_PROCESS_LINES"
fi

echo ""
echo "--- Kernel Taint Flags (Linux) ---"
if is_linux && [[ -f /proc/sys/kernel/tainted ]]; then
    taint=$(cat /proc/sys/kernel/tainted)
    echo "Taint value: $taint"
    if [[ "$taint" -ne 0 ]]; then
        echo "  (Non-zero taint means the kernel has loaded proprietary modules,"
        echo "   experienced errors, or other anomalies. Common with NVIDIA drivers.)"
    fi
fi

echo ""
echo "--- Disk I/O Stats ---"
if cmd_exists iostat; then
    safe_run "iostat" iostat -x 1 1 2>/dev/null | truncate_output 30
elif is_linux && [[ -f /proc/diskstats ]]; then
    echo "Raw diskstats:"
    cat /proc/diskstats 2>/dev/null | truncate_output 20
fi

echo ""
echo "--- Loaded Kernel Modules (notable) ---"
if is_linux; then
    lsmod 2>/dev/null | head -30
fi

echo ""
echo "--- SELinux / AppArmor Denials ---"
if is_linux; then
    if cmd_exists getenforce; then
        echo "SELinux: $(getenforce 2>/dev/null || echo 'unknown')"
        if cmd_exists ausearch && is_root; then
            echo "Recent SELinux denials:"
            ausearch -m avc -ts recent 2>/dev/null | tail -n 20 || echo "[none]"
        fi
    fi
    if cmd_exists aa-status && is_root; then
        echo "AppArmor status:"
        aa-status 2>/dev/null | head -10
        echo "Recent AppArmor denials:"
        dmesg 2>/dev/null | grep -i "apparmor.*denied" | tail -n 10 || echo "[none]"
    fi
fi


# ======================= END OF REPORT ========================================
cat <<EOF

$DIVIDER
END OF DIAGNOSTIC DATA
$DIVIDER

Please analyze all sections above. Focus especially on:
- Repeated errors or patterns in the system logs
- Any hardware issues (disk SMART failures, memory errors, overheating)
- OOM kills or resource exhaustion
- Kernel panics or crash dumps
- Failed services that might cause instability
- Recently changed packages that might have introduced regressions

Provide your analysis as:
1. ROOT CAUSE ANALYSIS — what is most likely causing the crashes
2. IMMEDIATE FIXES — step-by-step commands to fix the most critical issues
3. PREVENTIVE MEASURES — what to do to stop this from happening again
4. HARDWARE ASSESSMENT — whether any hardware may need replacement

========================== END OF DIAGNOSTIC PROMPT ==========================
EOF

} > "$OUTPUT_FILE" 2>&1

# --------------- Summary ---------------
echo ""
echo "  Diagnostic complete!"
echo ""
echo "  Report saved to: $(pwd)/$OUTPUT_FILE"
echo "  Report size: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "  NEXT STEPS:"
echo "  1. Open $OUTPUT_FILE in a text editor"
echo "  2. Copy the entire contents"
echo "  3. Paste it into a new conversation with your AI assistant"
echo "  4. The AI will analyze the data and provide specific fixes"
echo ""
echo "$DIVIDER"
