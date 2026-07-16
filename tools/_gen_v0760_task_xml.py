"""Generate Windows Task Scheduler XML for yonaa_alert_monitor V007.62

V007.62 升级 (2026-07-16):
- Action 直接调 pythonw.exe (no-console), 不走 bat
- 不弹 cmd 窗口 (避免干扰用户工作)
- pythonw.exe 是 Windows 自带的 no-console Python 解释器
- 日志通过 --log-file 参数由 Python 自己写
"""
from pathlib import Path

PYTHONW = r'C:\Users\Administrator\AppData\Local\Python\bin\pythonw.exe'
SCRIPT = r'D:\filework\release-prep-worktree\tools\alert_monitor_v0760.py'
CONFIG = r'D:\filework\release-prep-worktree\tools\alert_monitor_config.json'
LOGFILE = r'D:\filework\release-prep-worktree\tools\alert_monitor_v0760.log'
WORKDIR = r'D:\filework\release-prep-worktree\tools'

XML = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>yonaa_admin</Author>
    <Description>yonaa infrastructure monitor (V007.62) - 9 P0 layered checks via pythonw.exe (no console, no popup). Pushes alerts to Feishu HAO group via App Bot API.</Description>
    <URI>\\yonaa_alert_monitor</URI>
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
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{PYTHONW}</Command>
      <Arguments>"{SCRIPT}" --config "{CONFIG}" --log-file "{LOGFILE}" --check-now</Arguments>
      <WorkingDirectory>{WORKDIR}</WorkingDirectory>
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

out = Path(r'd:\filework\release-prep-worktree\tools\yonaa_alert_monitor_v0762.xml')
with open(out, 'wb') as f:
    f.write(b'\xff\xfe')
    f.write(XML.encode('utf-16-le'))
print(f'[OK] {out} written, {out.stat().st_size} bytes')
print(f'    Command:     {PYTHONW}')
print(f'    Arguments:   "{SCRIPT}" --config ... --log-file ... --check-now')
