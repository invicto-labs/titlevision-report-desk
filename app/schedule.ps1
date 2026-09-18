param([string]$Python,[string]$App,[ValidateSet('Enable','Disable')][string]$Mode)
$ErrorActionPreference='Stop'
$taskName='TitleVision Report Desk - Daily'
if($Mode -eq 'Disable') { if(Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue){Disable-ScheduledTask -TaskName $taskName | Out-Null}; exit }
if((Get-TimeZone).Id -ne 'India Standard Time'){throw 'Set this computer to India time before enabling the 8:45 AM schedule.'}
$hiddenPython=Join-Path (Split-Path $Python) 'pythonw.exe'
if(-not (Test-Path -LiteralPath $hiddenPython)){$hiddenPython=$Python}
$taskAction=New-ScheduledTaskAction -Execute $hiddenPython -Argument ('"'+(Join-Path $App 'server.py')+'" --scheduled') -WorkingDirectory $App
$taskTrigger=New-ScheduledTaskTrigger -Daily -At '08:45'
$taskPrincipal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$taskSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description 'Collect yesterday TitleVision errors at 08:45 India time without AI tokens. Requires this Windows user signed in and the computer awake.' -Force | Out-Null
