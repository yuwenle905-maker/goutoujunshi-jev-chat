# Windows 原生微信助手维护入口

用户要求每次更新在本地记录修改内容；最新调整为开发期间暂停逐版推送，最终版本完成后再统一同步整个修改计划与源码。

- 源码与使用说明：[integrations/wechat_desktop](../integrations/wechat_desktop/README.md)
- 每版修改记录：[CHANGELOG](../integrations/wechat_desktop/CHANGELOG.md)
- 完整开发计划及验收项：[DEVELOPMENT_PLAN](../integrations/wechat_desktop/DEVELOPMENT_PLAN.md)
- 版本、源码提交、程序校验和验证状态：[VERSION.json](../integrations/wechat_desktop/VERSION.json)
- 协作约定：[AGENTS](../AGENTS.md)

当前版本0.7.0：新增六页侧栏/圆角原生界面、全局人设与每联系人独立覆盖；原有44处业务操作回调保留。独立关系阶段/目标、长期记忆、修改学习、关系分析、多对象自动关联、人工审核/5秒确认及后台发送功能见源码README。

版本推进：0.6.4修正Qt点击抢前台并完成3轮文件传输助手后台实发；0.6.5增加全部监听对象自动关联；0.7.0完成界面与人设，传输文件保持不变。最终源码/EXE均230项回归和六页初始化通过。本轮未重新微信实发或真实模型调用；历史实测不能冒充本版新实测，最小化/锁屏及其他联系人仍不扩张验证结论。

2026-10-25用户明确授权将最新代码和功能备注上传GitHub，因此本次执行统一同步。后续仍按“开发期间本地记录，最终版本再统一同步”的偏好处理，不自动逐次推送。每次维护更新CHANGELOG、开发计划和VERSION；不上传个人数据、原始诊断包、聊天截图、API Key或运行数据库。

既有Jev Windows/QQ助手保持在 integrations/jev_windows，本次新增程序没有替换它。仓库源码同步不等于旧Release文件已自动更新。
