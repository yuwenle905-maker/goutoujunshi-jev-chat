# 阿乐跨App悬浮进程

TrollStore专用，独立root HUD，未向微信、抖音或SpringBoard注入动态库。
主App仅在用户点“开启／刷新”后启动。配置、模型Key、记忆密钥通过匿名管道传入进程内存，不写启动参数、环境变量或快照文件。
共享长期记忆继续AES-GCM与文件锁。HUD写入的本App记忆文件归还原mobile uid，主App/键盘仍可读取。不会遍历其他App数据目录。

HUD可切换本次启动快照内对象，读取剪贴板文字/图片、主动请求当前屏幕截图、本地OCR、核对原文、复用GoutouPipeline及对象记忆生成候选、编辑复制、显式归档和学习修改。
主App保存新配置/人设后需要刷新HUD。截图失败提示复制/系统截图，不把空屏当识别成功。复制不代表发送。
锁屏隐藏并取消本轮模型任务；不提供后台锁屏代聊或自动发消息。

构建由tools/build_overlay.sh生成AleHUD，打包脚本单独签名HUD及主App启动权限。主App不会继承HUD截屏/事件权限；键盘/分享/截屏扩展权限保持原样。

## 验证边界
旧模拟器3项UI测试不是本私有托管进程的真机证明。ARM64编译、签名和静态检查通过后只能称“含系统级悬浮实现的待真机验收包”。iOS17.0/TrollStore上显示、点击拖动、透明区穿透、其他App截图、键盘编辑和复制必须实测。

## 来源和修改
- Vendor来自Lessica/TrollSpeed，commit a609be260c8261ead36509c3bc4ded8479da9c40，MIT，保留版权及LICENSE。
- 其中KIF触摸组件按文件原版权与Apache2.0，保留许可证。仅把全局输入事件转为本HUD内部UITouch，不向宿主App生成事件。
- 为避免无scene启动崩溃：TSEventFetcher从+load改为延迟+initialize，初始占位UITouch不访问场景；KIF scene访问改为可空firstObject。HUDMainApplication事件分发保留上游实现。
- Host.mm、HUD.swift和主App管道启动器为本项目集成代码。启动失败、未完成托管或缺私有接口时显示失败，不修改系统服务或自动重启设备。
