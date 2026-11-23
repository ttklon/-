"""Non-destructive comparison of present Windows Plug and Play devices."""
import json
import subprocess
import sys


def windows_devices():
    if sys.platform != 'win32':
        raise RuntimeError('Эта диагностика работает только в Windows.')
    command = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
               "Get-PnpDevice -PresentOnly -ErrorAction Stop | "
               "Select-Object InstanceId,FriendlyName,Class,Status | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, encoding='utf-8', errors='replace', timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'Не удалось получить список устройств Windows: {exc}') from exc
    if result.returncode != 0:
        raise RuntimeError('Ошибка Windows при получении устройств: ' + (result.stderr.strip() or str(result.returncode)))
    try:
        data = json.loads(result.stdout or '[]')
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError('неожиданный формат списка')
        return {d['InstanceId']: d for d in data if isinstance(d, dict) and d.get('InstanceId')}
    except (ValueError, TypeError) as exc:
        raise RuntimeError('Windows вернула некорректный список устройств.') from exc


def compare(before, after):
    return sorted((v for k, v in after.items() if k not in before),
                  key=lambda d: (d.get('FriendlyName') or '', d['InstanceId']))


def report(new):
    lines = ['Диагностика кресла — новые устройства после подключения USB',
             '', 'Новые устройства не обязательно относятся к креслу.', '']
    if not new:
        lines += ['Новых устройств не обнаружено.',
                  'Возможно, USB передаёт только питание, но этот тест не доказывает этого.',
                  'Другое объяснение — устройство не распознано или не появилось в момент сравнения.']
    else:
        for d in new:
            lines += [f"Имя: {d.get('FriendlyName') or 'Без имени'}",
                      f"Класс: {d.get('Class') or 'Неизвестен'}",
                      f"Состояние: {d.get('Status') or 'Неизвестно'}",
                      f"ID: {d['InstanceId']}", '']
        lines += ['Обнаружение устройства не подтверждает, что оно умеет управлять подсветкой.']
    lines += ['', 'ID устройств может содержать серийный номер: проверьте перед публикацией.']
    return '\n'.join(lines)


# Only fields needed to identify possible radio hardware are exported. Full
# PnP instance IDs are used inside PowerShell to look up drivers, but do not
# cross the process boundary. They can contain serials and Bluetooth addresses.
PC_INVENTORY_SCRIPT = r'''
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$ErrorActionPreference = 'Stop'
$result = [ordered]@{ System = $null; Board = $null; OS = $null; CPU = @(); Devices = @(); Warnings = @() }
try {
    $result.System = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model
} catch { $result.Warnings += 'Не удалось получить модель компьютера.' }
try {
    $result.Board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product
} catch { $result.Warnings += 'Не удалось получить модель материнской платы.' }
try {
    $result.OS = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture
} catch { $result.Warnings += 'Не удалось получить версию Windows.' }
try {
    $result.CPU = @(Get-CimInstance Win32_Processor | Select-Object Name)
} catch { $result.Warnings += 'Не удалось получить модель процессора.' }
$drivers = @{}
try {
    foreach ($driver in @(Get-CimInstance Win32_PnPSignedDriver)) {
        if ($driver.DeviceID -and -not $drivers.ContainsKey($driver.DeviceID)) {
            $drivers[$driver.DeviceID] = $driver
        }
    }
} catch { $result.Warnings += 'Не удалось получить версии драйверов.' }
try {
    $selected = @('Bluetooth', 'Net', 'USB', 'USBDevice', 'Ports', 'HIDClass', 'Unknown')
    $devices = @(Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in $selected -or -not $_.Class })
    $result.Devices = @(foreach ($device in $devices) {
        $hardware = ''
        if ($device.InstanceId -match '(?i)VID_([0-9a-f]{4})&PID_([0-9a-f]{4})') {
            $hardware = 'USB VID_' + $Matches[1].ToUpper() + '&PID_' + $Matches[2].ToUpper()
        } elseif ($device.InstanceId -match '(?i)VEN_([0-9a-f]{4})&DEV_([0-9a-f]{4})') {
            $hardware = 'PCI VEN_' + $Matches[1].ToUpper() + '&DEV_' + $Matches[2].ToUpper()
        }
        $driver = $drivers[$device.InstanceId]
        [ordered]@{ Class = $device.Class; Name = $device.FriendlyName; Status = $device.Status;
                    Manufacturer = $device.Manufacturer; Hardware = $hardware;
                    DriverVersion = if ($driver) { $driver.DriverVersion } else { $null };
                    DriverProvider = if ($driver) { $driver.DriverProviderName } else { $null } }
    })
} catch { $result.Warnings += 'Не удалось получить список устройств Plug and Play.' }
$result | ConvertTo-Json -Depth 5 -Compress
'''


def pc_inventory():
    """Collect local hardware inventory; no serials, full PnP IDs or network data."""
    if sys.platform != 'win32':
        raise RuntimeError('Сбор сведений о компьютере работает только в Windows.')
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', PC_INVENTORY_SCRIPT],
                                capture_output=True, encoding='utf-8', errors='replace', timeout=90,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'Не удалось собрать сведения Windows: {exc}') from exc
    if result.returncode:
        raise RuntimeError('Windows не смогла собрать сведения: ' + (result.stderr.strip() or str(result.returncode)))
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or not isinstance(data.get('Devices'), list):
            raise ValueError('неверный формат')
        return data
    except (ValueError, TypeError) as exc:
        raise RuntimeError('Windows вернула некорректные сведения о компьютере.') from exc


def pc_report(data):
    """Format a whitelist of safe fields; redact MAC-shaped strings in names."""
    import re
    def clean(value):
        if value is None or value == '':
            return 'не указано'
        text = str(value).replace('\r', ' ').replace('\n', ' ')
        text = re.sub(r'(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])', '[MAC скрыт]', text)
        return text
    def section(name):
        value = data.get(name)
        return value if isinstance(value, dict) else {}
    system, board, os = section('System'), section('Board'), section('OS')
    lines = ['CHAIRLIGHT — сведения о компьютере', '',
             'Компьютер: ' + clean(system.get('Manufacturer')) + ' / ' + clean(system.get('Model')),
             'Материнская плата: ' + clean(board.get('Manufacturer')) + ' / ' + clean(board.get('Product')),
             'Windows: ' + ' / '.join(clean(os.get(k)) for k in ('Caption', 'Version', 'BuildNumber', 'OSArchitecture'))]
    cpus = data.get('CPU') or []
    if isinstance(cpus, dict): cpus = [cpus]
    for cpu in cpus:
        if isinstance(cpu, dict): lines.append('Процессор: ' + clean(cpu.get('Name')))
    lines += ['', 'УСТРОЙСТВА: Bluetooth, сеть, USB, HID, порты и неопознанные',
              '(Показано наличие, но это не доказывает совместимость с RF пульта.)', '']
    devices = data.get('Devices') or []
    if not devices: lines.append('Устройства не найдены или недоступны.')
    for d in sorted((d for d in devices if isinstance(d, dict)), key=lambda d: (str(d.get('Class') or ''), str(d.get('Name') or ''))):
        lines += [f"[{clean(d.get('Class'))}] {clean(d.get('Name'))}",
                  '  Состояние: ' + clean(d.get('Status')) + '; производитель: ' + clean(d.get('Manufacturer')),
                  '  ID модели: ' + clean(d.get('Hardware')),
                  '  Драйвер: ' + clean(d.get('DriverProvider')) + ' / ' + clean(d.get('DriverVersion'))]
    warnings = data.get('Warnings') or []
    if warnings:
        lines += ['', 'Предупреждения:'] + ['- ' + clean(w) for w in warnings]
    lines += ['', 'Имена устройств могут содержать личные названия. Перед отправкой проверьте отчёт.',
              'Отчёт не доказывает, что компьютер может передавать сигналы пульта.']
    return '\n'.join(lines)
