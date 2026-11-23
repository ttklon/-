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
$result = [ordered]@{ System = $null; Board = $null; OS = $null; BIOS = $null;
    CPU = @(); RAM = @(); GPU = @(); Disks = @(); Devices = @(); Warnings = @() }
try { $result.System = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,SystemType,TotalPhysicalMemory }
catch { $result.Warnings += 'Не удалось получить сведения о компьютере.' }
try { $result.Board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product,Version }
catch { $result.Warnings += 'Не удалось получить сведения о материнской плате.' }
try { $result.OS = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture }
catch { $result.Warnings += 'Не удалось получить версию Windows.' }
try { $result.BIOS = Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,ReleaseDate }
catch { $result.Warnings += 'Не удалось получить сведения о BIOS.' }
try { $result.CPU = @(Get-CimInstance Win32_Processor | Select-Object Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed) }
catch { $result.Warnings += 'Не удалось получить сведения о процессоре.' }
try { $result.RAM = @(Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer,PartNumber,Capacity,Speed,ConfiguredClockSpeed,DeviceLocator) }
catch { $result.Warnings += 'Не удалось получить сведения об оперативной памяти.' }
try { $result.GPU = @(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion,VideoProcessor) }
catch { $result.Warnings += 'Не удалось получить сведения о видеокартах.' }
try { $result.Disks = @(Get-CimInstance Win32_DiskDrive | Select-Object Model,Size,InterfaceType,MediaType,FirmwareRevision) }
catch { $result.Warnings += 'Не удалось получить сведения о накопителях.' }
$drivers = @{}
try {
    foreach ($driver in @(Get-CimInstance Win32_PnPSignedDriver)) {
        if ($driver.DeviceID -and -not $drivers.ContainsKey($driver.DeviceID)) { $drivers[$driver.DeviceID] = $driver }
    }
} catch { $result.Warnings += 'Не удалось получить версии драйверов.' }
$present = @{}
$presentKnown = $false
try {
    foreach ($d in @(Get-PnpDevice -PresentOnly)) { if ($d.InstanceId) { $present[$d.InstanceId] = $true } }
    $presentKnown = $true
} catch { $result.Warnings += 'Не удалось определить, какие устройства подключены сейчас.' }
try {
    $devices = @(Get-PnpDevice)
    $result.Devices = @(foreach ($device in $devices) {
        $hardware = ''
        if ($device.InstanceId -match '(?i)VID_([0-9a-f]{4})&PID_([0-9a-f]{4})') {
            $hardware = 'USB VID_' + $Matches[1].ToUpper() + '&PID_' + $Matches[2].ToUpper()
        } elseif ($device.InstanceId -match '(?i)VEN_([0-9a-f]{4})&DEV_([0-9a-f]{4})') {
            $hardware = 'PCI VEN_' + $Matches[1].ToUpper() + '&DEV_' + $Matches[2].ToUpper()
            if ($device.InstanceId -match '(?i)SUBSYS_([0-9a-f]{8})') { $hardware += '&SUBSYS_' + $Matches[1].ToUpper() }
        } elseif ($device.InstanceId -match '(?i)^ACPI\\([A-Z0-9_]{3,16})(?:\\|$)') {
            $hardware = 'ACPI ' + $Matches[1].ToUpper()
        }
        $driver = if ($device.InstanceId) { $drivers[$device.InstanceId] } else { $null }
        $isPresent = if ($presentKnown -and $device.InstanceId) { $present.ContainsKey($device.InstanceId) } else { $null }
        [ordered]@{ Class = $device.Class; Name = $device.FriendlyName; Status = $device.Status;
                    Present = $isPresent; Manufacturer = $device.Manufacturer; Hardware = $hardware;
                    DriverVersion = if ($driver) { $driver.DriverVersion } else { $null };
                    DriverProvider = if ($driver) { $driver.DriverProviderName } else { $null } }
    })
} catch { $result.Warnings += 'Не удалось получить полный список устройств Plug and Play.' }
$result | ConvertTo-Json -Depth 6 -Compress
'''


def pc_inventory():
    """Collect local hardware inventory; no serials, full PnP IDs or network data."""
    if sys.platform != 'win32':
        raise RuntimeError('Сбор сведений о компьютере работает только в Windows.')
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', PC_INVENTORY_SCRIPT],
                                capture_output=True, encoding='utf-8', errors='replace', timeout=180,
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
    """Format selected, non-secret fields and flag limitations."""
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
    def items(name):
        value = data.get(name) or []
        if isinstance(value, dict): value = [value]
        return [item for item in value if isinstance(item, dict)]
    def format_fields(item, fields):
        return '; '.join(label + ': ' + clean(item.get(field)) for field, label in fields)
    system, board, os, bios = (section(name) for name in ('System', 'Board', 'OS', 'BIOS'))
    lines = ['CHAIRLIGHT — расширенные сведения о компьютере', '',
             'Компьютер: ' + format_fields(system, [('Manufacturer', 'производитель'), ('Model', 'модель'), ('SystemType', 'тип'), ('TotalPhysicalMemory', 'ОЗУ всего, байт')]),
             'Плата: ' + format_fields(board, [('Manufacturer', 'производитель'), ('Product', 'модель'), ('Version', 'версия')]),
             'Windows: ' + format_fields(os, [('Caption', 'название'), ('Version', 'версия'), ('BuildNumber', 'сборка'), ('OSArchitecture', 'архитектура')]),
             'BIOS: ' + format_fields(bios, [('Manufacturer', 'производитель'), ('SMBIOSBIOSVersion', 'версия'), ('ReleaseDate', 'дата')])]
    groups = [
        ('CPU', 'ПРОЦЕССОРЫ', [('Name', 'модель'), ('Manufacturer', 'производитель'), ('NumberOfCores', 'ядер'), ('NumberOfLogicalProcessors', 'потоков'), ('MaxClockSpeed', 'макс. МГц')]),
        ('RAM', 'ОПЕРАТИВНАЯ ПАМЯТЬ', [('Manufacturer', 'производитель'), ('PartNumber', 'модель'), ('Capacity', 'объём, байт'), ('Speed', 'скорость'), ('ConfiguredClockSpeed', 'текущая скорость'), ('DeviceLocator', 'слот')]),
        ('GPU', 'ВИДЕОКАРТЫ', [('Name', 'модель'), ('AdapterRAM', 'видеопамять, байт'), ('VideoProcessor', 'процессор'), ('DriverVersion', 'драйвер')]),
        ('Disks', 'НАКОПИТЕЛИ', [('Model', 'модель'), ('Size', 'размер, байт'), ('InterfaceType', 'интерфейс'), ('MediaType', 'тип'), ('FirmwareRevision', 'прошивка')]),
    ]
    for key, title, fields in groups:
        lines += ['', title]
        group = items(key)
        if not group: lines.append('Нет сведений.')
        for item in group: lines.append('- ' + format_fields(item, fields))
    devices = items('Devices')
    lines += ['', f'ВСЕ УСТРОЙСТВА PLUG AND PLAY: {len(devices)}',
              'Включая неподключённые. Наличие адаптера не доказывает совместимость с RF пульта.', '']
    if not devices: lines.append('Устройства не найдены или недоступны.')
    for d in sorted(devices, key=lambda d: (str(d.get('Class') or ''), str(d.get('Name') or ''))):
        present = 'да' if d.get('Present') is True else 'нет' if d.get('Present') is False else 'неизвестно'
        lines += [f"[{clean(d.get('Class'))}] {clean(d.get('Name'))}",
                  '  Подключено: ' + present + '; состояние: ' + clean(d.get('Status')) + '; производитель: ' + clean(d.get('Manufacturer')),
                  '  ID модели: ' + clean(d.get('Hardware')),
                  '  Драйвер: ' + clean(d.get('DriverProvider')) + ' / ' + clean(d.get('DriverVersion'))]
    warnings = data.get('Warnings') or []
    if warnings: lines += ['', 'Предупреждения:'] + ['- ' + clean(w) for w in warnings]
    lines += ['', 'Имена устройств могут содержать личные названия. Перед отправкой проверьте отчёт.',
              'Это список сведений, доступных Windows, а не гарантия обнаружения всех физических устройств.']
    return '\n'.join(lines)
