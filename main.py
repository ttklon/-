import concurrent.futures
import queue
import tkinter as tk
from tkinter import messagebox, filedialog

from diagnostics import windows_devices, compare, report

BG = '#101321'
PANEL = '#1b2033'
WHITE = '#eff2ff'
MUTED = '#aeb7d2'


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ChairLight — диагностика USB')
        self.geometry('900x720')
        self.minsize(700, 600)
        self.configure(bg=BG)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.before = None
        self.protocol('WM_DELETE_WINDOW', self.close)
        root = tk.Frame(self, bg=BG, padx=26, pady=22); root.pack(fill='both', expand=True)
        self.label(root, 'CHAIRLIGHT', 21, WHITE, True).pack(anchor='w')
        self.label(root, 'Диагностика подключения кресла по USB', 11, MUTED).pack(anchor='w', pady=(2, 14))
        panel = tk.Frame(root, bg=PANEL, padx=18, pady=15); panel.pack(fill='x')
        self.label(panel, 'Как проверить', 13, WHITE, True).pack(anchor='w')
        self.label(panel, '1. Отключите USB кресла от компьютера.\n'
                          '2. Нажмите «Снимок без кресла» и дождитесь завершения.\n'
                          '3. Подключите USB кресла, подождите 10 секунд и нажмите «Сравнить».',
                   11, MUTED, justify='left').pack(anchor='w', pady=(7, 10))
        row = tk.Frame(panel, bg=PANEL); row.pack(anchor='w')
        self.snapshot_btn = self.button(row, '1. Снимок без кресла', self.snapshot, '#8068ee')
        self.snapshot_btn.pack(side='left', padx=(0, 8))
        self.compare_btn = self.button(row, '2. Сравнить', self.check, '#3a4260')
        self.compare_btn.pack(side='left'); self.compare_btn.configure(state='disabled')
        self.status = self.label(root, 'Отключите кресло и сделайте снимок.', 10, MUTED)
        self.status.pack(anchor='w', pady=(12, 6))
        self.output = tk.Text(root, bg='#191e2e', fg=WHITE, insertbackground=WHITE,
                              relief='flat', padx=14, pady=12, wrap='word', font=('Consolas', 10))
        self.output.pack(fill='both', expand=True)
        self.output.insert('1.0', 'Здесь появятся результаты.\n\nПрограмма не управляет креслом: '
                           'она проверяет появление новых устройств в Windows. '
                           'USB может служить только для питания; этот тест не доказывает это окончательно.')
        self.output.configure(state='disabled')
        row = tk.Frame(root, bg=BG); row.pack(fill='x', pady=(12, 0))
        self.button(row, 'Копировать', self.copy, '#3a4260').pack(side='left', padx=(0, 8))
        self.button(row, 'Сохранить отчёт', self.save, '#3a4260').pack(side='left')
        self.label(root, 'Отчёт может содержать серийные номера устройств. Проверьте его перед отправкой.',
                   9, MUTED).pack(anchor='w', pady=(8, 0))
        self.after(100, self.poll)

    def label(self, parent, text, size, color, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent['bg'], fg=color,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, command, color):
        return tk.Button(parent, text=text, command=command, bg=color, fg=WHITE,
                         activebackground='#6757a8', activeforeground=WHITE, disabledforeground='#888da5',
                         relief='flat', padx=14, pady=8, font=('Segoe UI', 10, 'bold'), cursor='hand2')

    def run_scan(self, callback):
        self.snapshot_btn.configure(state='disabled'); self.compare_btn.configure(state='disabled')
        self.status.configure(text='Получаем список устройств Windows, подождите…')
        future = self.pool.submit(windows_devices)
        def done(f):
            try: self.events.put((callback, f.result(), None))
            except Exception as exc: self.events.put((callback, None, str(exc)))
        future.add_done_callback(done)

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
            self.output.insert('1.0', report(new)); self.output.configure(state='disabled')
            self.status.configure(text=f'Готово. Новых устройств: {len(new)}. Проверьте результат ниже.')
        self.run_scan(done)

    def poll(self):
        try:
            while True:
                callback, data, error = self.events.get_nowait()
                self.snapshot_btn.configure(state='normal')
                callback(data, error)
                self.compare_btn.configure(state='normal' if self.before is not None else 'disabled')
        except queue.Empty: pass
        self.after(100, self.poll)

    def copy(self):
        self.clipboard_clear(); self.clipboard_append(self.output.get('1.0', 'end-1c'))
        self.status.configure(text='Отчёт скопирован. Проверьте его перед отправкой.')

    def save(self):
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Текстовый файл', '*.txt')])
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
