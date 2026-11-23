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
