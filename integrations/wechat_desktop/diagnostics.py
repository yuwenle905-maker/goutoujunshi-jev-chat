"""Bounded diagnostic events: metadata only, never exception messages or locals."""
from collections import deque
import datetime as dt
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import traceback
import uuid
import zipfile


REASONS=[('剪贴板含图片','剪贴板非文字'),('剪贴板正被占用','剪贴板被占用'),
 ('后台准备','后台控件准备失败'),('后台控件不可用','后台控件能力不足，未降级前台'),('后台控件身份','后台输入框身份不匹配'),
 ('后台投递失败','定向窗口消息投递失败'),('后台输入','后台输入回读不一致'),
 ('此对象上次发送结果不明','上次发送结果不明，需核对后恢复'),('此对象已人工接管','人工接管，自动暂停但可审核发送'),
 ('无法读取剪贴板','剪贴板文字读取失败'),('剪贴板写入窗口','剪贴板写入窗口未初始化'),
 ('无法清理剪贴板','剪贴板清理失败'),('无法写入剪贴板','剪贴板写入失败'),
 ('微信输入框已有','输入框已有草稿'),('输入框回读不符','粘贴后回读不一致'),
 ('前台窗口已切换','目标未成为前台窗口'),('发送窗口身份','窗口标题/进程/大小变化'),
 ('此对象尚未绑定','未绑定发送窗口'),('不在工作时间','当前不在工作时段'),
 ('今日发送上限','发送上限达到'),('此对象正在等待','等待回执或人工接管'),
 ('建议已失效','回复任务过期'),('此建议需要人工','需要人工审核'),
 ('另一个对象正在','其他对象正在发送'),('总开关已关闭','总开关已关闭'),
 ('回复已失效','回复任务过期'),('请先生成','尚无可发送回复'),
 ('绑定的窗口已关闭','窗口已关闭'),('任务已取消','任务已取消'),
 ('生成任务已取消','生成任务已取消'),('生成超时','生成超时'),
 ('DeepSeek 请求超时','模型请求超时'),('DeepSeek 请求失败（HTTP 401','模型密钥认证失败'),
 ('DeepSeek 请求失败（HTTP 402','模型账号余额不足'),('DeepSeek 请求失败（HTTP 403','模型接口拒绝访问'),
 ('DeepSeek 请求失败（HTTP 429','模型请求频率限制'),('DeepSeek 请求失败','模型接口HTTP错误'),
 ('DeepSeek 网络','模型网络连接错误'),('API Key','模型密钥格式或认证问题')]
REASONS.extend([('模型没有返回规定 JSON','模型正文格式不是有效JSON'),('模型返回了空正文','模型正文为空'),
 ('模型输出达到长度上限','模型JSON被截断'),('模型回复结构不完整','模型字段缺失或类型错误'),
 ('模型未返回完整的关系评估','关系评估字段不完整'),('模型JSON包含重复字段','模型JSON重复字段')])


class Diagnostics:
    def __init__(self,folder,version):
        self.folder=Path(folder);self.version=version;self.session=uuid.uuid4().hex[:10]
        self.lock=threading.RLock();self.rows=deque(maxlen=500);self.file_error=False
        self.handler=None;self.count=0
        try:
            self.folder.mkdir(parents=True,exist_ok=True)
            previous=self.folder/'events.jsonl'
            if previous.exists():
                for line in previous.read_text(encoding='utf-8')[-1024*1024:].splitlines()[-150:]:
                    try:
                        row=json.loads(line)
                        if isinstance(row,dict) and all(k in row for k in ('time','level','event')):self.rows.append(row)
                    except ValueError:pass
            self.handler=RotatingFileHandler(self.folder/'events.jsonl',maxBytes=1024*1024,backupCount=2,encoding='utf-8')
            self.handler.setFormatter(logging.Formatter('%(message)s'))
        except OSError:self.file_error=True
        self.event('app_start',status='started')

    def event(self,event,level='INFO',person=None,job=None,**fields):
        allowed={'stage','status','mode','reason','exception_type','frames','winerror','elapsed_ms','input_length',
            'expected_length','foreground_hwnd','bound_hwnd','pid','expected_width','expected_height',
            'actual_width','actual_height','clipboard_formats','clipboard_step','count','attempt','finish_reason','content_length','reasoning_length','format_status',
            'node_count','input_count','mmui_count','input_failure','gate_original','gate_changed','gate_restored'}
        with self.lock:
            self.count+=1
            row={'time':dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='milliseconds'),
                 'version':self.version,'session':self.session,'event':event,'level':level}
            if person:row['object_tag']=hashlib.sha256(str(person).encode()).hexdigest()[:10]
            if job:row['task_tag']=hashlib.sha256(str(job).encode()).hexdigest()[:10]
            row.update({k:v for k,v in fields.items() if k in allowed and isinstance(v,(str,int,float,bool,list,type(None)))})
            self.rows.append(row)
            if self.handler:
                try:
                    record=logging.LogRecord('diagnostics',logging.INFO,'',0,json.dumps(row,ensure_ascii=False),(),None)
                    self.handler.emit(record);self.handler.flush()
                except OSError:self.file_error=True
            return row

    def error(self,event,exc,person=None,job=None,stage=None):
        # Do not serialize str(exc): HTTP/library exceptions can contain secrets.
        text=str(exc)
        reason=next((label for prefix,label in REASONS if text.startswith(prefix)),'请结合错误类型和阶段检查')
        frames=[f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(exc.__traceback__)[-10:]]
        return self.event(event,'ERROR',person,job,stage=stage,reason=reason,
            exception_type=type(exc).__name__,winerror=getattr(exc,'winerror',None),clipboard_step=getattr(exc,'clipboard_step',None),frames=frames,
            **{k:v for k,v in getattr(exc,'probe_details',{}).items() if k in ('node_count','input_count','mmui_count','input_failure','gate_original','gate_changed','gate_restored')})

    def text(self):
        with self.lock:return '\n'.join(json.dumps(r,ensure_ascii=False) for r in self.rows)

    def view_text(self):
        names={'approve_clicked':'点击确认发送','approve_cancelled':'取消了审核确认','approve_confirmed':'已审核确认',
            'send_dispatch_requested':'进入发送前检查','send_attempt_reserved':'已登记发送尝试','send_stage':'发送阶段',
            'send_window_bound':'窗口绑定完成','send_waiting_receipt':'已按发送键，等待本机记录',
            'send_receipt_confirmed':'已核对本机发送记录','send_transport_error':'窗口操作失败',
            'send_worker_error':'发送未完成','send_preflight_blocked':'发送前置检查未通过',
            'send_condition_blocked':'条件检查未通过','send_conditions_checked':'条件检查结束（未发送）',
            'reply_ready':'回复已生成，等待审核或自动发送判断',
            'model_response_received':'模型响应元数据（不含正文）','model_format_rejected':'模型输出格式未通过，检查是否修复',
            'send_window_resized':'窗口尺寸变化，已重新计算底部输入位置','send_blocked_before_enter':'发送键未按下，已阻止本轮但未暂停后续新消息',
            'auto_generation_blocked':'此对象已暂停，需核对微信后恢复自动处理','follow_auto_selected':'已自动定位来信对象',
            'send_result_unknown':'发送结果不明，停止重试','send_failed_shown':'失败原因已显示',
            'ui_action_error':'界面操作错误','model_generation_error':'模型生成失败','logs_cleared':'旧日志已清空',
            'manual_takeover_detected':'检测到用户自行发送消息，自动处理暂停','auto_processing_resumed':'用户核对后恢复自动处理',
            'send_popup_shown':'发送确认弹窗已显示','send_popup_confirmed':'发送弹窗已确认','send_popup_cancelled':'发送弹窗已取消'}
        stages={'clipboard_prepare':'检查剪贴板','activate_window':'激活微信窗口','verify_foreground':'确认目标在前台',
            'background_prepare':'准备后台控件','background_read_draft':'后台检查已有草稿','background_set_value':'后台填写回复',
            'submit_background':'调用后台发送动作','background_submitted':'后台发送动作已提交',
            'focus_input':'聚焦已绑定输入框','check_existing_draft':'检查已有草稿','paste_reply':'粘贴回复','clipboard_retry':'剪贴板暂不可用，短暂重试',
            'verify_pasted_text':'核对粘贴文本','press_enter':'按Enter发送','enter_submitted':'Enter已提交',
            'delivery_preflight':'检查开关/时段/人工接管','verify_bound_window':'核验绑定窗口','database_receipt':'等待本机消息回读'}
        lines=[]
        with self.lock:
            for row in self.rows:
                lines.append(f"{row['time']} [{row['level']}] {names.get(row['event'],row['event'])} ({row['event']})")
                fields={k:v for k,v in row.items() if k not in ('time','level','event','session','version')}
                if 'stage' in fields:fields['stage']=stages.get(fields['stage'],fields['stage'])
                lines.append('  '+json.dumps(fields,ensure_ascii=False))
        return '\n'.join(lines)

    def export(self,path):
        with self.lock:
            if self.handler:self.handler.flush()
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('说明.txt','诊断包仅含运行事件、阶段、匿名对象/任务标识、错误类型和栈位置。没有聊天正文、微信号、窗口标题或API密钥。\n')
                z.writestr('current-session.jsonl',self.text())
                if self.folder.exists():
                    for file in sorted(self.folder.glob('events.jsonl*')):
                        if file.is_file():z.write(file,'logs/'+file.name)

    def clear(self):
        # Exact owned filenames only, serialized with writers and export.
        with self.lock:
            if self.handler:self.handler.close();self.handler=None
            failure=None
            try:
                for name in ('events.jsonl.2','events.jsonl.1','events.jsonl'):
                    (self.folder/name).unlink(missing_ok=True)
                self.rows.clear();self.file_error=False
            except OSError as exc:failure=exc
            finally:
                try:
                    self.handler=RotatingFileHandler(self.folder/'events.jsonl',maxBytes=1024*1024,backupCount=2,encoding='utf-8')
                    self.handler.setFormatter(logging.Formatter('%(message)s'))
                except OSError:
                    self.file_error=True
                    if failure is None:raise
            if failure is not None:raise failure
            self.event('logs_cleared',status='cleared')

    def close(self):
        if self.handler:self.handler.close();self.handler=None
