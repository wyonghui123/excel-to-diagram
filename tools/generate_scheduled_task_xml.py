#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_scheduled_task_xml.py - 计划任务 XML 模板生成器 (V007.86d)

V007.86c 教训 (V007.86b §6.2 + 6.3):
- 计划任务 XML 必须 UTF-16 LE + FFFE BOM (schtasks /Create 唯一接受)
- 必须用 .bat wrapper (有 --check-now + --log-file)
- 直接调 pythonw.exe 缺 --check-now → 走 main() else → return 1
- V007.79c latin1 fallback 错乱 (转换 UTF-16 LE 文件失败)

V007.86d 这个工具:
- 输入: task name + script name + 配置
- 输出: 干净 UTF-16 LE XML, 用 .bat wrapper
- 可以用 schtasks /Create /XML file.xml 重建任务

用法:
    py tools/generate_scheduled_task_xml.py ^
        --task-name "yonaa_alert_monitor" ^
        --script "alert_monitor_v0760.bat" ^
        --description "yonaa infrastructure monitor" ^
        --output "yonaa_alert_monitor.xml"

    py tools/generate_scheduled_task_xml.py ^
        --task-name "yonaa_log_service_check" ^
        --script "log_service_check.bat" ^
        --description "log_service check every 5min" ^
        --interval-min 5 ^
        --start-boundary "2026-07-17T09:30:00" ^
        --output "log_service_check.xml"
"""
import os
import sys
import argparse
from pathlib import Path


# User SID (V007.86b 用的)
DEFAULT_USER_SID = "S-1-5-21-820486380-1826441420-2207609957-500"


def generate_xml(
    task_name: str,
    script_bat: str,
    description: str,
    workdir: str,
    user_sid: str = DEFAULT_USER_SID,
    interval_min: int = 5,
    start_boundary: str = None,
) -> str:
    """Generate clean UTF-16 LE XML content for a scheduled task

    Args:
        task_name: Windows task name (e.g. '\\yonaa_alert_monitor')
        script_bat: Absolute path to .bat file (e.g. 'D:\\tools\\foo.bat')
        description: Task description
        workdir: Working directory
        user_sid: Windows user SID
        interval_min: Repeat interval in minutes
        start_boundary: Start boundary in ISO format (default: now + 1 min)

    Returns:
        UTF-16 LE XML string (no BOM)
    """
    import datetime
    if start_boundary is None:
        # Default: now + 1 min
        now = datetime.datetime.now() + datetime.timedelta(minutes=1)
        start_boundary = now.strftime('%Y-%m-%dT%H:%M:%S')

    # No need to escape backslashes for XML (XML doesn't treat \ as special)
    script_bat_x = script_bat
    workdir_x = workdir
    task_name_x = task_name

    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>yonaa_admin</Author>
    <Description>{description}</Description>
    <URI>{task_name_x}</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <Repetition>
        <Interval>PT{interval_min}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>{start_boundary}</StartBoundary>
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
      <Command>{script_bat_x}</Command>
      <WorkingDirectory>{workdir_x}</WorkingDirectory>
    </Exec>
  </Actions>
  <Principals>
    <Principal id="Author">
      <UserId>{user_sid}</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
</Task>
'''
    return xml


def write_xml(xml_content: str, output_path: str) -> int:
    """Write XML as UTF-16 LE with FFFE BOM

    Returns:
        bytes written
    """
    # Encode to UTF-16 LE
    xml_bytes = xml_content.encode('utf-16-le')
    # Add FFFE BOM
    xml_bytes = b'\xff\xfe' + xml_bytes
    with open(output_path, 'wb') as f:
        f.write(xml_bytes)
    return len(xml_bytes)


def main():
    parser = argparse.ArgumentParser(
        description='V007.86d Generate Scheduled Task XML (UTF-16 LE, .bat wrapper)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
V007.86d 故事:
  V007.86b 多次尝试修复 plan task 失败:
    - v1: Out-File 加 CRLF 破坏 UTF-16 LE (失败)
    - v2: 直接 pythonw.exe 没 --check-now (走 main() else return 1)
    - v3: 用 alert_monitor.bat (V007.58 老, 没用 v0760.py V007.60 分层)
    - v4: 用 alert_monitor_v0760.bat (有 --check-now + --log-file)  ← 正确
  V007.86d 加这个工具, 自动生成干净 v4-style XML

V007.86d 用法:
  py tools/generate_scheduled_task_xml.py ^
      --task-name "\\yonaa_alert_monitor" ^
      --script "D:\\filework\\worktrees\\release-prep\\tools\\alert_monitor_v0760.bat" ^
      --workdir "D:\\filework\\worktrees\\release-prep\\tools" ^
      --description "yonaa infrastructure monitor" ^
      --output "yonaa_alert_monitor.xml"

  schtasks /Create /TN "\\yonaa_alert_monitor" /XML yonaa_alert_monitor.xml /F
        '''
    )
    parser.add_argument('--task-name', required=True,
                        help='Task name (e.g. \\yonaa_alert_monitor)')
    parser.add_argument('--script', required=True,
                        help='Absolute path to .bat script (must have --check-now)')
    parser.add_argument('--workdir', required=True,
                        help='Working directory')
    parser.add_argument('--description', required=True,
                        help='Task description')
    parser.add_argument('--user-sid', default=DEFAULT_USER_SID,
                        help=f'User SID (default: {DEFAULT_USER_SID})')
    parser.add_argument('--interval-min', type=int, default=5,
                        help='Repeat interval in minutes (default: 5)')
    parser.add_argument('--start-boundary', default=None,
                        help='Start boundary in ISO format (default: now + 1 min)')
    parser.add_argument('--output', required=True,
                        help='Output XML file path')

    args = parser.parse_args()

    print('=' * 60)
    print('V007.86d Generate Scheduled Task XML')
    print('=' * 60)
    print()
    print(f'Task name:        {args.task_name}')
    print(f'Script:           {args.script}')
    print(f'Workdir:          {args.workdir}')
    print(f'Description:      {args.description}')
    print(f'User SID:         {args.user_sid}')
    print(f'Interval:         {args.interval_min} min')
    print(f'Start boundary:   {args.start_boundary or "(now + 1 min)"}')
    print(f'Output:           {args.output}')
    print()

    # Verify script exists
    if not os.path.exists(args.script):
        print(f'[FAIL] Script not found: {args.script}')
        sys.exit(2)
    if not args.script.lower().endswith('.bat'):
        print(f'[WARN] Script is not .bat (V007.86d best practice: use .bat wrapper)')
        print(f'       (Reason: v0760.py needs --check-now, .bat wrapper provides it)')

    # Verify workdir exists
    if not os.path.isdir(args.workdir):
        print(f'[FAIL] Workdir not found: {args.workdir}')
        sys.exit(2)

    # Generate
    xml_content = generate_xml(
        task_name=args.task_name,
        script_bat=args.script,
        description=args.description,
        workdir=args.workdir,
        user_sid=args.user_sid,
        interval_min=args.interval_min,
        start_boundary=args.start_boundary,
    )

    # Write
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = write_xml(xml_content, str(output_path))

    # Verify
    data = open(str(output_path), 'rb').read()
    if data[:2] == b'\xff\xfe':
        print(f'[OK] UTF-16 LE BOM (FFFE) verified')
    else:
        print(f'[FAIL] BOM incorrect: {data[:2].hex()}')
        sys.exit(2)

    text = data.decode('utf-16-le')
    if args.script in text:
        print(f'[OK] Script path in XML: {args.script}')
    else:
        print(f'[FAIL] Script path not in XML!')
        sys.exit(2)

    print()
    print(f'[OK] XML written: {output_path} ({bytes_written} bytes)')
    print()
    print('Next step:')
    print(f'  schtasks /Create /TN "{args.task_name}" /XML "{output_path}" /F')


if __name__ == '__main__':
    main()
