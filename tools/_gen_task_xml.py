"""Generate Windows Task Scheduler XML for yonaa_alert_monitor
- Triggers every 5 minutes, indefinite
- Run with highest privileges, whether user logged on or not
- 3 env vars embedded directly so we don't depend on system env
"""
import json
from pathlib import Path

XML = r'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>yonaa_admin</Author>
    <Description>yonaa infrastructure monitor (V007.59) - polls 7 services every 5 min, pushes alerts to Feishu HAO group via App Bot API.</Description>
    <URI>\yonaa_alert_monitor</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-07-16T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>D:\filework\worktrees/release-prep\tools\alert_monitor.bat</Command>
      <WorkingDirectory>D:\filework\worktrees/release-prep\tools</WorkingDirectory>
    </Exec>
  </Actions>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-21-820486380-1826441420-2207609957-500</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
</Task>
'''

out = Path(r'd:\filework\worktrees/release-prep\tools\yonaa_alert_monitor.xml')
# Write as UTF-16 (Task Scheduler requires UTF-16 LE with BOM)
with open(out, 'wb') as f:
    f.write(b'\xff\xfe')  # BOM
    f.write(XML.encode('utf-16-le'))
print(f'[OK] {out} written, {out.stat().st_size} bytes')
