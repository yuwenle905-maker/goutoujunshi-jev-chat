"""Modeless per-message approval. Five idle seconds confirm; interaction pauses."""
import math
import time
import tkinter as tk
from tkinter import ttk


class SendConfirmation:
    def __init__(self,master,contact,incoming,reply,valid,on_send,on_cancel,on_close,
                 allow_timeout=True,clock=time.monotonic,show=True):
        self.valid=valid;self.on_send=on_send;self.on_cancel=on_cancel;self.on_close=on_close
        self.clock=clock;self.allow_timeout=allow_timeout;self.deadline=None;self.timer=None
        self.completed=False;self.interacted=False;self.editing=False
        self.window=tk.Toplevel(master);self.window.withdraw();self.window.title('发送确认 · '+contact)
        self.window.geometry('620x560');self.window.minsize(520,460)
        self.window.attributes('-topmost',True)
        panel=ttk.Frame(self.window,padding=14);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='针对 '+contact+' 的信息',font=('Microsoft YaHei UI',12,'bold'),wraplength=580).pack(anchor='w')
        incoming_text=tk.Text(panel,height=5,wrap='word',font=('Microsoft YaHei UI',11))
        incoming_text.insert('1.0',incoming or '当前对象最近来信（无可显示文字）');incoming_text.configure(state='disabled');incoming_text.pack(fill='x',pady=8)
        ttk.Label(panel,text='回复如下：').pack(anchor='w')
        self.text=tk.Text(panel,height=7,wrap='word',font=('Microsoft YaHei UI',11));self.text.insert('1.0',reply)
        self.text.configure(state='disabled');self.text.pack(fill='both',expand=True,pady=8)
        self.status=tk.StringVar(value='正在显示发送确认…')
        ttk.Label(panel,textvariable=self.status,wraplength=580,foreground='#984300').pack(anchor='w',pady=5)
        row=ttk.Frame(panel);row.pack(fill='x')
        ttk.Button(row,text='确认发送',command=lambda:self.accept(True)).pack(side='left')
        ttk.Button(row,text='修改（停止倒计时）',command=self.modify).pack(side='left',padx=8)
        ttk.Button(row,text='取消本条',command=self.cancel).pack(side='right')
        self.window.protocol('WM_DELETE_WINDOW',self.cancel)
        self.window.bind('<ButtonPress>',self.interact,add=True);self.window.bind('<KeyPress>',self.interact,add=True)
        self.window.bind('<Escape>',lambda event:self.cancel(),add=True)
        if show:self.window.deiconify();self.window.after_idle(self.start)

    def start(self):
        if self.completed:return
        if not self.window.winfo_viewable():self.timer=self.window.after(100,self.start);return
        if self.allow_timeout and not self.interacted:self.deadline=self.clock()+5
        self.tick()

    def interact(self,event=None):
        if self.completed:return
        self.interacted=True;self.deadline=None
        self.status.set('倒计时已停止；请修改后确认发送，或取消本条。')

    def modify(self):
        self.interact();self.editing=True;self.text.configure(state='normal');self.text.focus_set()

    def tick(self):
        self.timer=None
        if self.completed:return
        if not self.valid():self.cancel('来信、对象或开关已变化，已取消本条。');return
        if self.deadline is not None:
            remaining=self.deadline-self.clock()
            if remaining<=0:self.accept(False);return
            self.status.set(f'{math.ceil(remaining)} 秒内无操作将默认确认并后台发送。点击修改或在弹窗中操作会停止倒计时。')
        elif not self.interacted:self.status.set('本条需要人工复核，不默认发送；请确认、修改或取消。')
        self.timer=self.window.after(100,self.tick)

    def accept(self,user_clicked=True):
        if self.completed:return
        if not self.valid():self.cancel('回复已失效，已取消本条。');return
        body=self.text.get('1.0','end-1c').strip()
        if not body:self.interact();self.status.set('回复不能为空；请点击修改后填写。');return
        self.finish();self.on_send(body,user_clicked or self.editing)

    def cancel(self,reason='用户取消本条回复。'):
        if self.completed:return
        self.finish();self.on_cancel(reason)

    def finish(self):
        if self.completed:return
        self.completed=True
        if self.timer:
            try:self.window.after_cancel(self.timer)
            except tk.TclError:pass
        self.window.destroy();self.on_close()
