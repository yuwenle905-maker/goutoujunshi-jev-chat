"""Read selected web-edition settings; never transfer automatic-send flags."""
import json
from pathlib import Path
from core import UserError
from runtime import split_targets

def read_web_settings(path):
    path=Path(path)
    if not path.is_file():raise UserError('没有找到网页版配置文件。0.3.0窗口版原有数据会直接沿用，不需要导入。')
    if path.stat().st_size>1_000_000:raise UserError('配置文件过大，未读取。')
    try:data=json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError,UnicodeError):raise UserError('网页版配置格式不正确，未修改原文件。') from None
    if not isinstance(data,dict):raise UserError('网页版配置必须为JSON对象。')
    web=data.get('wechat',{});llm=data.get('llm',{})
    if not isinstance(web,dict) or not isinstance(llm,dict):raise UserError('网页版配置字段格式异常。')
    aliases=web.get('aliases',[])
    if isinstance(aliases,list) and all(isinstance(v,str) for v in aliases):aliases=','.join(aliases)
    if not isinstance(aliases,str):raise UserError('联系人列表格式异常。')
    aliases=split_targets(aliases);mode=web.get('watch_mode','specified')
    if mode not in ('specified','recent'):raise UserError('未知的监听模式。')
    connection={'aliases':aliases,'watch_mode':mode,'account':str(web.get('account') or '自动识别'),
                'data_path':str(web.get('data_path') or Path.home()/'Documents/xwechat_files')}
    warnings=[]
    if mode=='specified' and not aliases:
        connection=None;warnings.append('网页版联系人列表为空，未覆盖当前列表，请在窗口重新填写并保存一次。')
    model=None
    base_url=llm.get('base_url','https://api.deepseek.com')
    if isinstance(base_url,str) and base_url.rstrip('/') in ('https://api.deepseek.com','https://api.deepseek.com/v1'):
        if isinstance(llm.get('api_key'),str) and llm['api_key'].strip():
            model={'key':llm['api_key'].strip(),'model':str(llm.get('model') or ''),'network':'直连 DeepSeek','models':[]}
    else:warnings.append('网页版使用自定义模型地址，窗口版只连接DeepSeek官方，未导入该密钥。')
    return {'connection':connection,'model':model,'warning':' '.join(warnings)}
