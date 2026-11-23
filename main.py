import concurrent.futures
import queue
import tkinter as tk
from tkinter import messagebox, filedialog

from diagnostics import windows_devices, compare, report, pc_inventory, pc_report
from clipboard_win import copy_text
from usb_hubs import windows_hubs, hub_report

BG = '#101321'
PANEL = '#1b2033'
WHITE = '#eff2ff'
MUTED = '#aeb7d2'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ChairLight — диагностика компьютера')
        self.geometry('1000x800')
        self.minsize(700, 600)
        self.configure(bg=BG)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.before = None
        self.protocol('WM_DELETE_WINDOW', self.close)
        root = tk.Frame(self, bg=BG, padx=26, pady=22); root.pack(fill='both', expand=True)
        self.label(root, 'CHAIRLIGHT', 21, WHITE, True).pack(anchor='w')
        self.label(root, 'Сведения о компьютере и диагностика USB кресла', 11, MUTED).pack(anchor='w', pady=(2, 14))
        panel = tk.Frame(root, bg=PANEL, padx=18, pady=15); panel.pack(fill='x')
        self.label(panel, 'Сведения о компьютере', 13, WHITE, True).pack(anchor='w')
        self.label(panel, 'Компоненты и устройства всех классов, включая отключённые. Отчёт никуда не отправляется.',
                   10, MUTED, justify='left').pack(anchor='w', pady=(4, 6))
        self.inventory_btn = self.button(panel, 'Собрать сведения о компьютере', self.inventory, '#8068ee')
        self.inventory_btn.pack(anchor='w', pady=(0, 3))
        self.hubs_btn = self.button(panel, 'Проверить возможности USB-портов (без отключения)', self.hubs, '#3a4260')
        self.hubs_btn.pack(anchor='w', pady=(0, 10))
        self.label(panel, 'Дополнительно: проверка USB кресла', 12, WHITE, True).pack(anchor='w')
        self.label(panel, '1. Отключите USB кресла от компьютера.\n'
                          '2. Нажмите «Снимок без кресла» и дождитесь завершения.\n'
                          '3. Подключите USB кресла, подождите 10 секунд и нажмите «Сравнить».',
                   11, MUTED, justify='left').pack(anchor='w', pady=(7, 10))
        row = tk.Frame(panel, bg=PANEL); row.pack(anchor='w')
        self.snapshot_btn = self.button(row, '1. Снимок без кресла', self.snapshot, '#8068ee')
        self.snapshot_btn.pack(side='left', padx=(0, 8))
        self.compare_btn = self.button(row, '2. Сравнить', self.check, '#3a4260')
        self.compare_btn.pack(side='left'); self.compare_btn.configure(state='disabled')
        self.status = self.label(root, 'Нажмите «Собрать сведения о компьютере».', 10, MUTED)
        self.status.pack(anchor='w', pady=(12, 6))
        row = tk.Frame(root, bg=BG); row.pack(fill='x', pady=(0, 8))
        self.button(row, 'Копировать весь отчёт', self.copy, '#3a4260').pack(side='left', padx=(0, 8))
        self.button(row, 'Сохранить TXT', self.save, '#8068ee').pack(side='left')
        self.label(root, 'Отчёт можно выделить, отредактировать или сохранить. Проверьте его перед отправкой.',
                   9, MUTED).pack(anchor='w', pady=(0, 8))
        output_frame = tk.Frame(root, bg=BG); output_frame.pack(fill='both', expand=True)
        scrollbar = tk.Scrollbar(output_frame); scrollbar.pack(side='right', fill='y')
        self.output = tk.Text(output_frame, bg='#191e2e', fg=WHITE, insertbackground=WHITE,
                              relief='flat', padx=14, pady=12, wrap='word', font=('Consolas', 10), height=6,
                              undo=True, yscrollcommand=scrollbar.set)
        self.output.pack(side='left', fill='both', expand=True); scrollbar.configure(command=self.output.yview)
        self.output.insert('1.0', 'Здесь появятся результаты. Программа не управляет креслом.\n\n'
                           'Проверьте отчёт перед отправкой: имена устройств могут быть личными.')
        self.output.bind('<Control-a>', self.select_all)
        self.output.bind('<Control-A>', self.select_all)
        self.after(100, self.poll)

    def label(self, parent, text, size, color, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent['bg'], fg=color,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, command, color):
        return tk.Button(parent, text=text, command=command, bg=color, fg=WHITE,
                         activebackground='#6757a8', activeforeground=WHITE, disabledforeground='#888da5',
                         relief='flat', padx=14, pady=8, font=('Segoe UI', 10, 'bold'), cursor='hand2')

    def run_scan(self, callback, operation=windows_devices):
        self.snapshot_btn.configure(state='disabled'); self.compare_btn.configure(state='disabled')
        self.inventory_btn.configure(state='disabled'); self.hubs_btn.configure(state='disabled')
        self.status.configure(text='Получаем сведения Windows, подождите…')
        future = self.pool.submit(operation)
        def done(f):
            try: self.events.put((callback, f.result(), None))
            except Exception as exc: self.events.put((callback, None, str(exc)))
        future.add_done_callback(done)

    def inventory(self):
        def done(data, error):
            if error:
                self.status.configure(text='Сбор сведений не выполнен.')
                messagebox.showerror('Ошибка', error); return
            self.output.configure(state='normal'); self.output.delete('1.0', 'end')
            self.output.insert('1.0', pc_report(data))
            self.output.see('1.0')
            self.status.configure(text='Готово. Проверьте отчёт, затем скопируйте или сохраните его.')
        self.run_scan(done, pc_inventory)

    def hubs(self):
        def done(data, error):
            if error:
                self.status.configure(text='Проверка USB-концентраторов не выполнена.')
                messagebox.showerror('Ошибка', error); return
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', hub_report(data))
            self.output.see('1.0')
            self.status.configure(text='Проверка завершена без отключения USB. Скопируйте или сохраните отчёт.')
        self.run_scan(done, windows_hubs)

    def snapshot(self):
        def done(devices, error):
            if error:
                self.status.configure(text='Снимок не выполнен.')
                messagebox.showerror('Ошибка', error); return
            self.before = devices
            self.status.configure(text='Снимок сохранён. Подключите кресло, подождите 10 секунд и нажмите «Сравнить».')
        self.run_scan(done)

    def check(self):
        if self.before is None: return
        def done(devices, error):
            if error:
                self.status.configure(text='Сравнение не выполнено.')
                messagebox.showerror('Ошибка', error); return
            new = compare(self.before, devices)
            self.output.configure(state='normal'); self.output.delete('1.0', 'end')
            self.output.insert('1.0', report(new))
            self.status.configure(text=f'Готово. Новых устройств: {len(new)}. Проверьте результат ниже.')
        self.run_scan(done)

    def poll(self):
        try:
            while True:
                callback, data, error = self.events.get_nowait()
                self.snapshot_btn.configure(state='normal')
                self.inventory_btn.configure(state='normal'); self.hubs_btn.configure(state='normal')
                callback(data, error)
                self.compare_btn.configure(state='normal' if self.before is not None else 'disabled')
        except queue.Empty: pass
        self.after(100, self.poll)

    def select_all(self, event=None):
        self.output.tag_add('sel', '1.0', 'end-1c')
        return 'break'

    def copy(self):
        try:
            copy_text(self.output.get('1.0', 'end-1c'), self.winfo_id())
            self.status.configure(text='Отчёт скопирован. Вставьте его с помощью Ctrl+V.')
        except Exception as exc:
            self.status.configure(text='Копирование не удалось. Можно сохранить отчёт в TXT.')
            messagebox.showerror('Ошибка копирования', str(exc) + '\n\nПопробуйте кнопку «Сохранить TXT».')

    def save(self):
        path = filedialog.asksaveasfilename(defaultextension='.txt', initialfile='ChairLight-report.txt', filetypes=[('Текстовый файл', '*.txt')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f: f.write(self.output.get('1.0', 'end-1c'))
                self.status.configure(text='Отчёт сохранён.')
            except OSError as exc: messagebox.showerror('Ошибка сохранения', str(exc))

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
