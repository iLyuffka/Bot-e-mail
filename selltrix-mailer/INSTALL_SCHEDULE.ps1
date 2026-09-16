param(
    [switch]$ConfirmApprovedRecipients,
    [switch]$ConfirmStopListReviewed
)

if (-not $ConfirmApprovedRecipients -or -not $ConfirmStopListReviewed) {
    throw "Run only after reviewing consent and the stop-list: pass both confirmation switches."
}

$base = $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "$base\RUN_SCHEDULED.bat" -WorkingDirectory $base
$trigger = New-ScheduledTaskTrigger -Daily -At 10:00
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable:$false -ExecutionTimeLimit (New-TimeSpan -Hours 8)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "SelltrixMailer" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
Write-Host "Task SelltrixMailer installed for the current logged-in Windows user."
