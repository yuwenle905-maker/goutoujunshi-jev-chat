"""Explicit expression preferences; never replace evidence or relationship boundaries."""
from core import UserError

DEFAULT_PERSONA={'enabled':True,'description':'自然、温和、有主见，适度幽默，不刻意显得博学。',
    'expression':'短句，顺着话题回应；少用套话、感叹号和说教，参考我真实的用词与标点。',
    'avoid':'不要主动邀请电话、语音或视频。不编造我的经历、位置、承诺或已经做过的事。'}


def normalize(value):
    if not isinstance(value,dict):raise UserError('人设设置格式不正确。')
    result={'enabled':bool(value.get('enabled',True))}
    for field in ('description','expression','avoid'):
        text=value.get(field,'')
        if not isinstance(text,str):raise UserError('人设内容应为文字。')
        if len(text)>1500:raise UserError('每项人设最多1500字，请精简后保存。')
        result[field]=text.strip()
    return result


def resolve(global_value,profile):
    global_value=normalize(global_value)
    if not global_value['enabled']:return {}
    if profile.get('persona_override',False):
        return normalize({'enabled':True,'description':profile.get('persona_description',''),
            'expression':profile.get('persona_expression',''),'avoid':profile.get('persona_avoid','')})
    return global_value
