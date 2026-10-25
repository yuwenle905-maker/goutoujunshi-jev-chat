# Windows 原生微信助手维护入口

用户要求整个修改计划同步至本仓库，今后每次更新备注改了什么。

- 源码与使用说明：[integrations/wechat_desktop](../integrations/wechat_desktop/README.md)
- 每版修改记录：[CHANGELOG](../integrations/wechat_desktop/CHANGELOG.md)
- 完整开发计划及验收项：[DEVELOPMENT_PLAN](../integrations/wechat_desktop/DEVELOPMENT_PLAN.md)
- 版本、源码提交、程序校验和验证状态：[VERSION.json](../integrations/wechat_desktop/VERSION.json)
- 协作约定：[AGENTS](../AGENTS.md)

当前0.6.3修正独立窗口输入框标签为通用“输入”导致的误拦截：改用严格的进程和UIA根窗口归属核验。真实微信后台投递仍待验收。每次修改后同步更新上述记录，不上传个人数据、原始诊断包或聊天截图。

既有Jev Windows/QQ助手保持在 integrations/jev_windows，本次新增程序没有替换它。仓库源码同步不等于旧Release文件已自动更新。
