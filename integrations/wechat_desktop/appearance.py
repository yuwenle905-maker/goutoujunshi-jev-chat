"""Presentation only. Keep the existing notebook, widgets and business callbacks."""
import tkinter as tk
from tkinter import ttk

BG='#e6edf8'
SURFACE='#f8faff'


def setup(root):
    root.configure(background=BG)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',font=('Microsoft YaHei UI',10),background=SURFACE,foreground='#29364b')
    style.configure('TFrame',background=SURFACE)
    style.configure('TLabel',background=SURFACE,foreground='#35435a')
    style.configure('TButton',padding=(12,8),background='#edf2fb',foreground='#405678',borderwidth=0,
        lightcolor='#ffffff',darkcolor='#edf2fb',focuscolor='#b9caeb')
    style.map('TButton',background=[('pressed','#dce6f8'),('active','#e3ebfa')],foreground=[('disabled','#9ba6b9')])
    style.configure('TEntry',padding=7,fieldbackground='#ffffff',bordercolor='#e0e7f2',lightcolor='#e0e7f2',darkcolor='#e0e7f2')
    style.configure('TCombobox',padding=6,fieldbackground='#ffffff',background='#e8effb',bordercolor='#e0e7f2',arrowsize=13)
    style.map('TCombobox',fieldbackground=[('readonly','#ffffff')],selectbackground=[('readonly','#e6edfb')],selectforeground=[('readonly','#35435a')])
    style.configure('TCheckbutton',background=SURFACE,padding=(0,5),indicatorbackground='#ffffff')
    style.map('TCheckbutton',background=[('active',SURFACE)])
    style.configure('TRadiobutton',background=SURFACE,padding=(0,4))
    style.configure('TNotebook',background=BG,borderwidth=0,tabmargins=0)
    # Only the main notebook hides its tabs; memory sub-tabs stay visible.
    style.configure('Workspace.TNotebook',background=BG,borderwidth=0)
    style.layout('Workspace.TNotebook.Tab',[])
    style.configure('TNotebook.Tab',padding=(15,8),background='#e9eff9',borderwidth=0)
    style.map('TNotebook.Tab',background=[('selected','#ffffff')],foreground=[('selected','#4166bb')])
    style.configure('Sidebar.TFrame',background=BG)
    style.configure('Sidebar.TLabel',background=BG,foreground='#74839c')
    style.configure('Nav.TButton',background=BG,foreground='#687a96',anchor='w',padding=(18,13))
    style.configure('ActiveNav.TButton',background='#ffffff',foreground='#4168bc',anchor='w',padding=(18,13),font=('Microsoft YaHei UI',10,'bold'))
    style.map('Nav.TButton',background=[('active','#f2f6fd')])
    style.configure('Primary.TButton',background='#5879c4',foreground='white',padding=(15,9))
    style.map('Primary.TButton',background=[('active','#4a6cb7'),('pressed','#405fa5')],foreground=[('disabled','#b7c4df')])
    # Nine-slice images round only the button surface; native Button semantics,
    # focus traversal and the existing commands remain unchanged.
    images=[]
    def rounded(color):
        image=tk.PhotoImage(master=root,width=24,height=24)
        for y in range(24):
            for x in range(24):
                cx=min(max(x,8),15);cy=min(max(y,8),15)
                if (x-cx)**2+(y-cy)**2<=64:image.put(color,(x,y))
        images.append(image);return image
    for name,colors in [('TButton',('#edf2fb','#e3ebfa','#dce6f8')),('Primary.TButton',('#5879c4','#4a6cb7','#405fa5')),
                        ('Nav.TButton',(BG,'#f2f6fd','#e2eafa')),('ActiveNav.TButton',('#ffffff','#f9fbff','#eaf0fb'))]:
        normal,hover,pressed=[rounded(c) for c in colors]
        element='Rounded'+name+str(root.winfo_id())
        style.element_create(element,'image',normal,('pressed',pressed),('active',hover),border=9,padding=0,sticky='nswe')
        style.layout(name,[(element,{'sticky':'nswe','children':[('Button.padding',{'sticky':'nswe','children':[('Button.focus',{'sticky':'nswe','children':[('Button.label',{'sticky':'nswe'})]})]})]})])
        backing=BG if name in ('Nav.TButton','ActiveNav.TButton') else SURFACE
        style.configure(name,background=backing)
        style.map(name,background=[('active',backing),('pressed',backing)])
    root._appearance_images=images
    style.configure('Heading.TLabel',font=('Microsoft YaHei UI',21,'bold'),foreground='#2b3851')
    return style


def workspace(app):
    """Return the existing six-page notebook with a new sidebar shell."""
    root=app.root
    ttk.Label(root,textvariable=app.status,padding=(20,10),wraplength=1200,background=BG,foreground='#687e9f').pack(fill='x',side='bottom')
    body=ttk.Frame(root,style='Sidebar.TFrame');body.pack(fill='both',expand=True)
    sidebar=ttk.Frame(body,style='Sidebar.TFrame',padding=(16,25),width=190)
    sidebar.pack(side='left',fill='y');sidebar.pack_propagate(False)
    ttk.Label(sidebar,text='狗头微信助手',style='Sidebar.TLabel',font=('Microsoft YaHei UI',14,'bold'),foreground='#2f4364').pack(anchor='w',pady=(0,2))
    ttk.Label(sidebar,text='关系 · 记忆 · 表达',style='Sidebar.TLabel',font=('Microsoft YaHei UI',9)).pack(anchor='w',pady=(0,30))
    area=ttk.Frame(body,style='Sidebar.TFrame',padding=(4,18,20,12));area.pack(side='left',fill='both',expand=True)
    heading=ttk.Frame(area,padding=(18,13));heading.pack(fill='x',pady=(0,10))
    title=tk.StringVar(value='微信与对象');ttk.Label(heading,textvariable=title,style='Heading.TLabel').pack(side='left')
    ttk.Label(heading,textvariable=app.policy_status,foreground='#73839c',wraplength=430).pack(side='right',padx=8)
    ttk.Label(area,text='发送前逐条确认 · 5秒无操作默认发送 · 点击修改停止倒计时',
        padding=(18,10),background='#eef3fc',foreground='#687e9f').pack(fill='x',pady=(0,10))
    book=ttk.Notebook(area,style='Workspace.TNotebook');book.pack(fill='both',expand=True)
    buttons={}
    for name in ('微信与对象','回复工作台','长期记忆','模型与规则','行为设置','诊断日志'):
        button=ttk.Button(sidebar,text=name,style='Nav.TButton',command=lambda name=name:book.select(app.tabs[name]))
        button.pack(fill='x',pady=3);buttons[name]=button
    ttk.Label(sidebar,text='本机加密保存\n独立关系档案\n人工审核 / 自动发送',style='Sidebar.TLabel',font=('Microsoft YaHei UI',9),justify='left').pack(side='bottom',anchor='w',pady=10)
    def changed(event=None):
        for name,button in buttons.items():
            active=name in app.tabs and book.select()==str(app.tabs[name])
            button.configure(style='ActiveNav.TButton' if active else 'Nav.TButton')
            if active:title.set(name)
    book.bind('<<NotebookTabChanged>>',changed,add='+')
    app.navigation_buttons=buttons
    return book
