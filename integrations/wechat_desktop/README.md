# 狗头微信助手 · Windows 原生版

版本0.6.3。同一已登录微信账号监听多个对象，每人独立关系阶段、目标、背景、历史与审核修改学习。使用Tk原生窗口，DeepSeek官方模型接口；可生成建议、人工审核，以及开启逐条5秒默认确认的自动模式。

**状态：源码和最终EXE 209项隔离测试通过；真实微信后台投递仍待验收。** 当前“输入”通用标签兼容采用进程/窗口父链核验，尚不能把检查成功当作发送成功。未接入抖音，也没有完成后台Hook发送。

- [完整使用说明](README.txt)
- [每次更新记录](CHANGELOG.md)
- [开发计划与真实设备验收项](DEVELOPMENT_PLAN.md)
- [协作与同步要求](AGENTS.md)

本目录是新增的独立实现，不替换已有 integrations/jev_windows。源码运行/构建需Windows和包含Tk的Python3.14，本机已验证该版本：

```powershell
python -m pip install -r requirements-build.txt
python app.py
./build.ps1 -Python python
```

构建输出在 dist/GoutouWechat.exe。数据默认保存在当前用户LOCALAPPDATA下的GoutouWechatAssistant；不要将运行数据库、聊天、API Key、截图或诊断包提交到仓库。自动发送默认关闭；首次仍需核对微信资料，将对应联系人与独立窗口关联。后台发送不得抢前台、占鼠标或剪贴板；未知结果暂停，不盲目重复。

项目整体许可沿用仓库根LICENSE；打包的Skill及vendor下第三方组件另有随附许可证。版本校验值与测试状态由同步时生成的VERSION.json记录；该文件不代表真实微信实测已通过。
