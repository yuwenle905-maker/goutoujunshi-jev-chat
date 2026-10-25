"""狗头微信助手：原生窗口、多对象历史、关系分析与严格后台发送。"""
from __future__ import annotations
import argparse
import ctypes
import datetime as dt
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from core import VERSION, Store, ReplyQueue, UserError
from engine import Engine
from wechat_reader import WechatReader
from controller import Controller
from runtime import RELATIONSHIP_GOALS,RELATIONSHIP_STAGES

RESOURCES=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))


class App(Controller):
    def __init__(self, root, data_root):
        self.root=root;self.home=Path(data_root);self.home.mkdir(parents=True,exist_ok=True)
        self.store=Store(self.home/'memory.sqlite3')
        from diagnostics import Diagnostics
        self.diagnostics=Diagnostics(self.home/'logs',VERSION)
        self.reply_queue=ReplyQueue(self.store)
        self.engine=Engine(RESOURCES/'skill')
        self.events=queue.Queue();self.monitor=None;self.stop_event=threading.Event()
        self.person=None;self.profile=None;self.messages=[];self.binding=None
        self.current_job=None;self.closing=False
        self.model_busy=False;self.pending_auto=None
        root.title('狗头微信助手 '+VERSION+' · 审核 / 自动发送')
        root.geometry('1120x820');root.minsize(900,680)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background='#f4f5f7')
        style.configure('TFrame',background='#f4f5f7')
        style.configure('TButton',padding=(12,7))
        style.configure('TNotebook.Tab',padding=(15,8))
        self.status=tk.StringVar(value='未连接。请保持电脑版微信登录，输入准确微信号后开始。')
        self.model_settings=self.store.get('settings','model',{'key':'','model':''})
        self.data_path=tk.StringVar(value=str(Path.home()/'Documents/xwechat_files'))
        self.alias=tk.StringVar()
        self.stage=tk.StringVar(value='了解中');self.goal=tk.StringVar(value='自然接话')
        self.relation_state=tk.StringVar();self.assessment_enabled=tk.BooleanVar(value=True)
        self.memory=tk.BooleanVar(value=False);self.auto=tk.BooleanVar(value=False)
        self.identity=tk.StringVar(value='尚未绑定联系人')
        self.memory_status=tk.StringVar(value='长期记忆未启用')
        self.key=tk.StringVar(value=self.model_settings.get('key',''))
        self.model=tk.StringVar(value=self.model_settings.get('model',''))
        self.job_status=tk.StringVar(value='等待生成建议')
        self.resources=RESOURCES
        self.setup_runtime()
        self._build()
        self.install_runtime_hooks()
        root.report_callback_exception=self.callback_exception
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(150,self.tick)

    def _build(self):
        header=ttk.Frame(self.root,padding=16);header.pack(fill='x')
        ttk.Label(header,text='狗头微信助手',font=('Microsoft YaHei UI',22,'bold')).pack(side='left')
        ttk.Label(header,text='独立窗口 · 人工审核 / 自动发送',foreground='#ad5100').pack(side='right')
        banner=ttk.Label(self.root,text='发送前弹窗：5秒无操作默认确认；点击修改停止倒计时。仅向本次已绑定窗口的对象后台发送。',
                         padding=(18,9),background='#fff1d6',foreground='#734a00')
        banner.pack(fill='x')
        book=ttk.Notebook(self.root);book.pack(fill='both',expand=True,padx=16,pady=12)
        self.tabs={}
        for name in ('微信与对象','回复工作台','长期记忆','模型与规则','行为设置','诊断日志'):
            pane=ttk.Frame(book,padding=14);book.add(pane,text=name);self.tabs[name]=pane
        self.book=book
        p=self.scrollable_form(self.tabs['微信与对象'])
        ttk.Label(p,text='微信数据目录（包含各账号文件夹的 xwechat_files）').pack(anchor='w')
        row=ttk.Frame(p);row.pack(fill='x',pady=(4,12))
        ttk.Entry(row,textvariable=self.data_path).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='选择目录',command=self.pick_data).pack(side='left',padx=8)
        row=ttk.Frame(p);row.pack(fill='x',pady=3)
        ttk.Radiobutton(row,text='指定多位聊天对象',variable=self.watch_mode,value='specified',command=self.mode_changed).pack(side='left')
        ttk.Radiobutton(row,text='最近私聊（无需填写微信号）',variable=self.watch_mode,value='recent',command=self.mode_changed).pack(side='left',padx=12)
        ttk.Label(row,text='本机账号').pack(side='left',padx=8)
        self.account_box=ttk.Combobox(row,textvariable=self.account_choice,values=['自动识别'],state='readonly',width=24)
        self.account_box.pack(side='left')
        ttk.Button(row,text='刷新账号目录',command=self.refresh_accounts).pack(side='left',padx=4)
        ttk.Label(p,text='聊天对象微信号 / 内部 ID：多个以逗号分隔；监听中更改后自动刷新').pack(anchor='w')
        row=ttk.Frame(p);row.pack(fill='x',pady=5)
        self.alias_widget=ttk.Entry(row,textvariable=self.alias,width=46);self.alias_widget.pack(side='left')
        self.connect_button=ttk.Button(row,text='连接 / 刷新聊天',command=self.connect)
        self.connect_button.pack(side='left',padx=8)
        ttk.Button(row,text='停止监听 / 取消任务',command=self.stop).pack(side='left')
        ttk.Button(row,text='保存监听列表',command=self.save_connection).pack(side='left',padx=5)
        ttk.Label(p,textvariable=self.identity,wraplength=960,padding=(0,10),foreground='#075d9a').pack(fill='x')
        ttk.Label(p,textvariable=self.connection_status,wraplength=960,foreground='#734a00').pack(fill='x')
        row=ttk.Frame(p);row.pack(fill='x',pady=5)
        ttk.Label(row,text='正在编辑的对象').pack(side='left')
        self.profile_box=ttk.Combobox(row,textvariable=self.conversation,state='readonly',width=58)
        self.profile_box.pack(side='left',padx=8)
        self.profile_box.bind('<<ComboboxSelected>>',lambda event:self.choose_person(widget=self.profile_box))
        row=ttk.Frame(p);row.pack(fill='x',pady=10)
        ttk.Label(row,text='阶段').pack(side='left')
        ttk.Combobox(row,textvariable=self.stage,values=RELATIONSHIP_STAGES,width=14).pack(side='left',padx=8)
        ttk.Label(row,text='目标').pack(side='left',padx=8)
        ttk.Combobox(row,textvariable=self.goal,values=RELATIONSHIP_GOALS,width=20).pack(side='left')
        row=ttk.Frame(p);row.pack(fill='x',pady=4)
        ttk.Label(row,text='此对象当前状态').pack(side='left')
        ttk.Entry(row,textvariable=self.relation_state,width=64).pack(side='left',padx=8)
        ttk.Checkbutton(p,text='针对这个对象评估关系信号、未知与边界，再生成回复（同一次模型请求）',variable=self.assessment_enabled).pack(anchor='w')
        ttk.Label(p,text='此对象的背景与边界（独立保存，不套用其他人）').pack(anchor='w')
        self.notes=tk.Text(p,height=4,wrap='word',font=('Microsoft YaHei UI',11));self.notes.pack(fill='x',pady=5)
        ttk.Checkbutton(p,text='允许在本机加密保存此对象聊天；关闭后停止保存和召回，原数据保留',variable=self.memory).pack(anchor='w',pady=8)
        ttk.Button(p,text='保存此对象设置',command=self.save_profile).pack(anchor='w')
        ttk.Label(p,text='启动不会发送历史消息。你可以切换微信聊天；读取按已核验的内部 ID 进行。\n多个账号匹配时停止绑定，不选择第一个。读取与模型失败不会自动切换对象。',wraplength=950).pack(anchor='w',pady=15)
        ttk.Separator(p).pack(fill='x',pady=8)
        ttk.Label(p,text='严格后台发送：核对微信号并关联独立窗口，无需鼠标定位或保持前台；控件不可用则明确停止，不使用前台兜底。',foreground='#ad5100').pack(anchor='w')

        p=self.tabs['回复工作台']
        row=ttk.Frame(p);row.pack(fill='x')
        ttk.Checkbutton(row,text='新消息自动生成建议（仅提交对应对象的文字）',variable=self.auto,command=self.save_behavior).pack(side='left')
        ttk.Checkbutton(row,text='自动发送（弹窗5秒无操作默认确认）',variable=self.auto_send,command=self.save_behavior).pack(side='left',padx=12)
        ttk.Button(row,text='核对后恢复自动处理',command=self.resume).pack(side='right')
        row=ttk.Frame(p);row.pack(fill='x',pady=6)
        ttk.Label(row,text='当前查看的聊天对象').pack(side='left')
        self.conversation_box=ttk.Combobox(row,textvariable=self.conversation,state='readonly',width=62)
        self.conversation_box.pack(side='left',padx=8);self.conversation_box.bind('<<ComboboxSelected>>',self.choose_person)
        row=ttk.Frame(p);row.pack(fill='x')
        self.window_box=ttk.Combobox(row,textvariable=self.send_window,state='readonly',width=36)
        self.window_box.pack(side='left')
        ttk.Button(row,text='刷新微信窗口',command=self.refresh_send_windows).pack(side='left',padx=5)
        ttk.Button(row,text='设置发送窗口',command=self.setup_send_window).pack(side='left')
        ttk.Button(row,text='准备/检查后台控件（不发送）',command=self.probe_background).pack(side='left',padx=5)
        ttk.Label(p,textvariable=self.send_status,wraplength=980,foreground='#734a00').pack(anchor='w',pady=3)
        ttk.Label(p,textvariable=self.transport_status,wraplength=980,foreground='#ad5100').pack(anchor='w')
        row=ttk.Frame(p);row.pack(fill='x')
        ttk.Checkbutton(row,text='学习此对象审核修改（加密保存最近8次，不随聊天记忆开关）',variable=self.learning,command=self.save_learning).pack(side='left')
        ttk.Button(row,text='清除此对象风格示例',command=self.clear_learning).pack(side='left',padx=6)

        row=ttk.Frame(p);row.pack(fill='x')
        ttk.Checkbutton(row,text='新消息自动定位到对应对象（编辑中暂不打断）',variable=self.follow_messages,command=self.refresh_inbox).pack(side='left')
        ttk.Button(row,text='查看最新来信对象',command=self.view_latest_incoming).pack(side='right')
        ttk.Label(p,textvariable=self.inbox_status,wraplength=980,foreground='#075d9a').pack(anchor='w',pady=3)
        # Pack action controls before the expanding text panes: they must remain
        # reachable on short screens and at Windows 125/150% text scaling.
        row=ttk.Frame(p);row.pack(fill='x',pady=5)
        self.approve_button=ttk.Button(row,text='确认发送（当前编辑内容）',command=self.approve_send)
        self.approve_button.pack(side='left')
        ttk.Button(row,text='生成 / 重新生成',command=lambda:self.generate(False)).pack(side='left',padx=4)
        ttk.Button(row,text='复制建议',command=self.copy_reply).pack(side='left',padx=4)
        ttk.Button(row,text='取消生成',command=self.cancel_generation).pack(side='left',padx=4)
        ttk.Button(row,text='检查发送条件（不发送）',command=self.check_send_conditions).pack(side='left',padx=4)
        ttk.Label(p,textvariable=self.send_mode_status,wraplength=980,foreground='#734a00').pack(anchor='w')
        ttk.Label(p,textvariable=self.last_send_status,wraplength=980,foreground='#075d9a').pack(anchor='w',pady=3)
        panes=ttk.Panedwindow(p,orient='horizontal');panes.pack(fill='both',expand=True,pady=10)
        left=ttk.Frame(panes);right=ttk.Frame(panes);panes.add(left,weight=1);panes.add(right,weight=1)
        ttk.Label(left,textvariable=self.chat_header,wraplength=450).pack(anchor='w')
        ttk.Label(left,textvariable=self.new_message_status,wraplength=450,foreground='#075d9a').pack(anchor='w')
        self.chat=self.scrolled_text(left,height=15,readonly=True)
        ttk.Label(right,textvariable=self.job_status,wraplength=440).pack(anchor='w')
        self.reply=self.scrolled_text(right,height=9)
        self.reason=self.scrolled_text(right,height=5,readonly=True)

        p=self.tabs['长期记忆']
        ttk.Label(p,textvariable=self.memory_status,font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=5)
        row=ttk.Frame(p);row.pack(fill='x',pady=8)
        ttk.Button(row,text='保存本机当前已读取历史',command=self.import_current).pack(side='left')
        ttk.Button(row,text='导入聊天 JSON',command=self.import_file).pack(side='left',padx=8)
        ttk.Button(row,text='导出文字记录',command=self.export_memory).pack(side='left')
        ttk.Button(row,text='清除此对象聊天与摘要',command=self.clear_memory).pack(side='right')
        memory_tabs=ttk.Notebook(p);memory_tabs.pack(fill='both',expand=True)
        summary_page=ttk.Frame(memory_tabs,padding=6);review_page=ttk.Frame(memory_tabs,padding=6)
        memory_tabs.add(summary_page,text='长期摘要');memory_tabs.add(review_page,text='关系分析与推进')
        p=summary_page
        ttk.Label(p,text='长期摘要（生成草稿后请核对、编辑，再保存）').pack(anchor='w',pady=8)
        self.summary=self.scrolled_text(p,height=15)
        row=ttk.Frame(p);row.pack(fill='x',pady=8)
        ttk.Button(row,text='根据已保存记录生成摘要草稿',command=lambda:self.generate(True)).pack(side='left')
        ttk.Button(row,text='保存已核对摘要',command=self.save_summary).pack(side='left',padx=8)
        ttk.Label(p,text='聊天、摘要、草稿和 API Key 使用当前 Windows 用户的 DPAPI 加密。\n记忆没有云同步；调用模型时会发送所选对象近期文字、背景与摘要。运行期间有临时解密数据库，正常停止会清理。',wraplength=970).pack(anchor='w',pady=10)
        row=ttk.Frame(review_page);row.pack(fill='x')
        ttk.Button(row,text='分析关系、痛点与推进建议',command=self.analyze_relationship).pack(side='left')
        ttk.Button(row,text='取消分析',command=self.cancel_review).pack(side='left',padx=8)
        ttk.Label(review_page,text='只使用当前对象的历史分时段抽样、近期文字与已确认摘要，提交给所选模型。\n分析包括原话依据、关系现状、沟通痛点、注意事项及推进/放缓建议；按对象加密保存，不自动修改关系设置或发送。',wraplength=960).pack(anchor='w',pady=8)
        ttk.Label(review_page,textvariable=self.review_status,wraplength=960).pack(anchor='w')
        self.review_text=self.scrolled_text(review_page,height=18,readonly=True)

        p=self.tabs['模型与规则']
        ttk.Label(p,text='DeepSeek 官方 API Key（本机加密保存）').pack(anchor='w')
        ttk.Entry(p,textvariable=self.key,show='•',width=75).pack(anchor='w',pady=8)
        ttk.Label(p,text='模型（从你的账号获取列表，也可直接输入准确模型名）').pack(anchor='w')
        row=ttk.Frame(p);row.pack(fill='x',pady=8)
        self.model_box=ttk.Combobox(row,textvariable=self.model,values=self.model_settings.get('models',[]),width=42);self.model_box.pack(side='left')
        self.fetch_button=ttk.Button(row,text='获取可用模型',command=self.fetch_models);self.fetch_button.pack(side='left',padx=8)
        ttk.Button(row,text='保存模型设置',command=self.save_model).pack(side='left')
        ttk.Label(p,textvariable=self.model_fetch_status,wraplength=950,foreground='#075d9a').pack(anchor='w',pady=5)
        row=ttk.Frame(p);row.pack(fill='x',pady=4)
        ttk.Label(row,text='模型网络方式').pack(side='left')
        ttk.Combobox(row,textvariable=self.network,values=['直连 DeepSeek','跟随系统代理'],state='readonly',width=25).pack(side='left',padx=8)
        ttk.Label(p,text='此版本仅连接 https://api.deepseek.com，不转发 API Key 给其他域名。\n模型列表由接口返回，不将“免费”或某个型号写死。配置完成后才可生成建议。',wraplength=950).pack(anchor='w',pady=12)
        ttk.Separator(p).pack(fill='x',pady=12)
        ttk.Label(p,text=f'内置完整 SKILL.md + {len(self.engine.references)} 份参考文档',font=('Microsoft YaHei UI',13,'bold')).pack(anchor='w')
        ttk.Label(p,text='主规则完整进入提示词；按场景选2–3份参考，单份最多8000字。\n当前是本机安装时的规则快照，尚无自动同步功能。没有执行 Skill 内的命令或脚本。\n模型只能返回结构化建议；解析失败不把整段分析当回复。',wraplength=950).pack(anchor='w',pady=12)
        ttk.Label(p,text='数据位置：'+str(self.home),wraplength=950).pack(anchor='w',pady=12)
        ttk.Button(p,text='从网页版导入联系人列表和 DeepSeek 设置（不导入发送开关）',command=self.import_web_settings).pack(anchor='w')
        p=self.tabs['行为设置']
        ttk.Label(p,text='代聊行为',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w',pady=10)
        ttk.Checkbutton(p,text='功能总开关（关闭后停止读取并取消全部任务）',variable=self.enabled,command=self.toggle_enabled).pack(anchor='w',pady=8)
        ttk.Checkbutton(p,text='新消息自动生成回复建议',variable=self.auto,command=self.save_behavior).pack(anchor='w',pady=8)
        ttk.Checkbutton(p,text='自动发送（逐条弹窗，5秒无操作默认发送；关闭后需先点击确认发送）',variable=self.auto_send,command=self.save_behavior).pack(anchor='w',pady=8)
        row=ttk.Frame(p);row.pack(fill='x',pady=12)
        ttk.Label(row,text='工作时间（北京时间）').pack(side='left')
        ttk.Entry(row,textvariable=self.hour_start,width=5).pack(side='left',padx=8)
        ttk.Label(row,text='—').pack(side='left')
        ttk.Entry(row,textvariable=self.hour_end,width=5).pack(side='left',padx=8)
        ttk.Label(row,text='时；相同表示全天，支持跨午夜').pack(side='left')
        row=ttk.Frame(p);row.pack(fill='x',pady=10)
        ttk.Label(row,text='每日回复 / 发送上限').pack(side='left')
        ttk.Entry(row,textvariable=self.daily_limit,width=8).pack(side='left',padx=8)
        ttk.Label(row,text='0表示不限；共用上限，建议与发送尝试分别计数，未知结果也占发送额度').pack(side='left')
        row=ttk.Frame(p);row.pack(fill='x',pady=12)
        ttk.Label(row,text='未设置对象的默认阶段').pack(side='left')
        ttk.Combobox(row,textvariable=self.default_stage,values=['刚认识','了解中','暧昧','伴侣'],width=12).pack(side='left',padx=8)
        ttk.Label(row,text='默认目标').pack(side='left')
        ttk.Combobox(row,textvariable=self.default_goal,values=RELATIONSHIP_GOALS,width=20).pack(side='left',padx=8)
        ttk.Button(p,text='保存行为设置',command=self.save_behavior).pack(anchor='w',pady=12)
        ttk.Label(p,textvariable=self.counter_status,font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=8)
        ttk.Label(p,textvariable=self.policy_status,wraplength=950).pack(anchor='w',pady=8)
        ttk.Label(p,text='一个登录账号可同时监听最多20位指定联系人；最近私聊模式读取最近100个联系人会话。\n未设置对象使用默认目标，只在内存中保留近期聊天；只有明确开启记忆的对象才长期保存聊天/草稿。\n工作时间和上限控制自动建议及全部发送；手动生成不计入建议上限。重启默认人工审核，需重新绑定窗口。',wraplength=950).pack(anchor='w',pady=12)
        p=self.tabs['诊断日志']
        ttk.Label(p,text='诊断日志',font=('Microsoft YaHei UI',18,'bold')).pack(anchor='w')
        ttk.Label(p,text='记录发送阶段、错误类型和代码位置；不记录正文、微信号、窗口标题或 API Key。\n日志最多3份，每份约1MB；可导出诊断包排查问题。',wraplength=970).pack(anchor='w',pady=8)
        row=ttk.Frame(p);row.pack(fill='x')
        ttk.Button(row,text='刷新日志',command=self.refresh_logs).pack(side='left')
        ttk.Button(row,text='打开日志目录',command=self.open_log_folder).pack(side='left',padx=6)
        ttk.Button(row,text='导出诊断包',command=self.export_diagnostics).pack(side='left')
        ttk.Button(row,text='清空日志',command=self.clear_logs).pack(side='left',padx=6)
        ttk.Label(p,text=str(self.diagnostics.folder),wraplength=970).pack(anchor='w',pady=5)
        self.log_text=self.scrolled_text(p,height=18,readonly=True)
        self.book.bind('<<NotebookTabChanged>>',lambda event:self.refresh_logs() if self.book.select()==str(self.tabs['诊断日志']) else None)
        ttk.Label(self.root,textvariable=self.status,relief='sunken',padding=9,wraplength=1050).pack(fill='x')

    def scrollable_form(self,parent):
        canvas=tk.Canvas(parent,background='#f4f5f7',highlightthickness=0)
        bar=ttk.Scrollbar(parent,orient='vertical',command=canvas.yview)
        bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=bar.set)
        frame=ttk.Frame(canvas);window=canvas.create_window((0,0),window=frame,anchor='nw')
        frame.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(window,width=event.width))
        def wheel(event):
            if isinstance(event.widget,tk.Misc) and str(event.widget).startswith(str(frame)) and event.widget.winfo_class() not in ('Text','TCombobox'):
                canvas.yview_scroll(-int(event.delta/120),'units')
        self.root.bind_all('<MouseWheel>',wheel,add='+')
        return frame

    def scrolled_text(self,parent,height=10,readonly=False):
        f=ttk.Frame(parent);f.pack(fill='both',expand=True,pady=5)
        text=tk.Text(f,height=height,wrap='word',font=('Microsoft YaHei UI',10),undo=not readonly,
                     relief='flat',padx=8,pady=8,background='white')
        bar=ttk.Scrollbar(f,orient='vertical',command=text.yview);bar.pack(side='right',fill='y')
        text.configure(yscrollcommand=bar.set);text.pack(fill='both',expand=True)
        if readonly:text.configure(state='disabled')
        return text

    @staticmethod
    def put(widget,text):
        state=str(widget.cget('state'));widget.configure(state='normal')
        widget.delete('1.0','end');widget.insert('1.0',text);widget.configure(state=state)

    def report(self,text):self.status.set(text)

    def show_error(self,exc):
        self.diagnostics.error('ui_action_error',exc,person=self.person,job=self.current_job,stage='ui_action')
        # Never display library diagnostics or HTTP payloads containing credentials.
        text=str(exc) if isinstance(exc,UserError) else f'操作失败（{type(exc).__name__}）；未修改微信或发送消息。'
        self.report(text)
        messagebox.showerror('操作未完成',text,parent=self.root)

    def pick_data(self):
        value=filedialog.askdirectory(title='选择 xwechat_files 目录',parent=self.root)
        if value:self.data_path.set(value)









    def import_current(self):
        if not self.person:return
        try:
            self.save_profile()
            if not self.memory.get():raise UserError('请先勾选允许保存此对象聊天，并保存设置。')
            if not messagebox.askyesno('保存此对象历史',f'将当前已读取的 {len(self.messages)} 条记录存入本机加密记忆？仅关联当前绑定对象，不会发送给模型。',parent=self.root):return
            count=self.store.remember(self.person,self.messages);self.update_memory();self.report(f'新增保存 {count} 条；相同来源消息不会重复保存。')
        except Exception as exc:self.show_error(exc)

    def import_file(self):
        if not self.person:self.show_error(UserError('请先连接目标对象。'));return
        try:
            if not self.store.get('objects',self.person,{}).get('memory'):raise UserError('请先开启并保存此对象的本机记忆设置。')
            path=filedialog.askopenfilename(parent=self.root,title='选择含 sender/message/timestamp 的聊天 JSON',filetypes=[('聊天 JSON','*.json')])
            if not path:return
            if Path(path).stat().st_size>2_000_000:raise UserError('导入文件不能超过2MB。')
            data=json.loads(Path(path).read_text(encoding='utf-8-sig'));rows=data if isinstance(data,list) else data.get('messages')
            if not isinstance(rows,list) or not rows:raise UserError('需要非空消息数组。')
            import hashlib
            batch=hashlib.sha256(Path(path).read_bytes()).hexdigest();parsed=[]
            for index,row in enumerate(rows):
                role={'me':'me','我':'me','other':'other','对方':'other'}.get(row.get('sender'))
                text=row.get('message');stamp=row.get('timestamp')
                if not role or not isinstance(text,str) or not isinstance(stamp,str):raise UserError('每条消息需 sender(me/other)、message 和真实 timestamp；未猜测缺失身份或时间。')
                date=dt.datetime.fromisoformat(stamp)
                if date.tzinfo is None:date=date.replace(tzinfo=dt.timezone(dt.timedelta(hours=8)))
                parsed.append({'id':f'import:{batch}:{index}','time':date.timestamp(),'seq':index,'role':role,'kind':1,'text':text,'type':'文本'})
            if not messagebox.askyesno('确认导入',f"将 {len(parsed)} 条消息保存到当前对象 {self.binding.get('remark') or self.binding['alias']}？\n不同来源文件与本地历史可能包含同一消息，本版不按相似文字删除。",parent=self.root):return
            count=self.store.remember(self.person,parsed);self.update_memory();self.report(f'导入 {count} 条；相同文件重复导入会去重。')
        except Exception as exc:self.show_error(exc)

    def export_memory(self):
        if not self.person:return
        try:
            rows=self.store.history(self.person)
            if not rows:raise UserError('记忆已暂停或没有已保存消息。')
            path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='聊天记忆明文导出.json')
            if not path:return
            if not messagebox.askyesno('明文导出','此文件不加密，可能包含私人聊天。确认保存到所选位置？',parent=self.root):return
            dest=Path(path);temp=dest.with_name(dest.name+'.new')
            temp.write_text(json.dumps({'messages':[{'sender':m['role'],'message':m['text'] if m['kind']==1 else '['+m['type']+']','timestamp':dt.datetime.fromtimestamp(m['time'],dt.timezone(dt.timedelta(hours=8))).isoformat()} for m in rows if m['role'] in ('me','other')]},ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temp,dest);self.report('已导出明文 JSON，请妥善保管。')
        except Exception as exc:self.show_error(exc)

    def clear_memory(self):
        if self.person and messagebox.askyesno('清除此对象记忆','只清除本程序保存的此对象聊天、摘要、关系分析和草稿；不修改微信。确认？',parent=self.root):
            try:
                person=self.person
                self.stop();self.store.clear_person(person)
                self.put(self.summary,'');self.put(self.review_text,'');self.review_status.set('此对象关系分析已清除。');self.current_job=None
                self.report('已清除此对象记忆；请停止并重新连接后继续监听。')
            except Exception as exc:self.show_error(exc)

    def save_summary(self):
        if not self.person:return
        try:
            if not self.store.get('objects',self.person,{}).get('memory'):raise UserError('记忆暂停中，未保存摘要。')
            self.profile['summary']=self.summary.get('1.0','end-1c')
            self.store.save('objects',self.person,self.profile);self.report('已保存核对后的摘要，之后分析会带入。')
        except Exception as exc:self.show_error(exc)









def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--self-test',metavar='REPORT')
    parser.add_argument('--ui-test',metavar='REPORT')
    parser.add_argument('--diagnose',metavar='WECHAT_ID')
    parser.add_argument('--wechat-data')
    parser.add_argument('--report')
    args=parser.parse_args()
    if args.ui_test:
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root=tk.Tk();root.withdraw()
            app=App(root,folder)
            root.update_idletasks()
            report={'tabs':list(app.tabs),'window_title':root.title(),'rule_references':len(app.engine.references),
                    'startup_connected':app.binding is not None,'startup_auto_suggestions':app.auto.get(),
                    'sender_available':True,'startup_auto_send':app.auto_send.get(),
                    'sender_implementation':'strict_background_messages','foreground_fallback':False}
            assert len(app.tabs)==6 and not app.binding and not app.enabled.get()
            app.close()
            Path(args.ui_test).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0
    if args.self_test:
        import unittest
        # Frozen entry scripts run as __main__; expose the same App to GUI tests.
        sys.modules.setdefault('app',sys.modules[__name__])
        suite=unittest.defaultTestLoader.discover(str(RESOURCES/'tests'))
        import io
        output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
        Path(args.self_test).write_text(output.getvalue(),encoding='utf-8')
        return 0 if result.wasSuccessful() else 1
    if args.diagnose:
        reader=None
        try:
            home=Path(args.data_dir or Path.cwd()/'diagnostic-data')
            reader=WechatReader(RESOURCES,args.wechat_data or Path.home()/'Documents/xwechat_files',home/'temporary')
            binding=reader.connect(args.diagnose);first=reader.read();second=reader.read()
            report={'exact_alias_match':binding['alias'].casefold()==args.diagnose.casefold(),
                    'account_identified':bool(binding['account']),'peer_identified':bool(binding['username']),
                    'records':len(first),'text_records':sum(m['kind']==1 for m in first),
                    'roles':{r:sum(m['role']==r for m in first) for r in ('me','other','unknown')},
                    'unchanged_snapshot_has_no_new_ids':not(set(m['id'] for m in second)-set(m['id'] for m in first)),
                    'sender_enabled':False,'scope':'only local read; no sending or model calls'}
            Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            if reader:reader.close()
        return 0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:pass
    root=tk.Tk()
    home=Path(args.data_dir) if args.data_dir else Path(os.environ['LOCALAPPDATA'])/'GoutouWechatAssistant'
    try:App(root,home)
    except Exception as exc:
        messagebox.showerror('程序启动未完成',str(exc) if isinstance(exc,UserError) else '启动失败（'+type(exc).__name__+'），原有数据未删除。',parent=root)
        root.destroy();return 1
    root.mainloop()
    return 0


if __name__=='__main__':sys.exit(main())
