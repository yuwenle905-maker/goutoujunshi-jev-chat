# iOS17 AleHUD 启动崩溃

用户两份2026-11-16报告一致：iOS17.0/21A327，SIGSEGV/KERN_INVALID_ADDRESS 0x8；主线程栈为UIEventFetcher.setEventFetcherSink → UIEventDispatcher.eventFetcherDidReceiveEvents → CFRunLoopSourceSignal，来自UIApplication.__completeAndRunAsPlugin。二进制UUID与1.1.2一致。原始报告仅留本机，不上传。

1.1.2错误地认为自建AX事件源能替代UIKit原生_collectHIDEventsRunLoopSource，在隐藏初始化方法不可见时仍绑定Fetcher并继续启动。

## 改动

- 从交付cbd26b0建独立fix分支，不混入a19233c实验。
- 先建立并核验UIKit原生source，再绑定Fetcher/进入plugin启动。
- 隐藏调用兼容两参数优化ABI(self,runLoop)与三参数ABI(self,_cmd,runLoop)。旧适配只识别mov x2，并不能处理省略_cmd的优化调用。
- 有界读取本进程UIKit代码，同映像、唯一匹配；从运行时ivar元数据获取_runLoop偏移，核验候选callee把对应runLoop参数写入该字段。未知指令、参数错误和歧义均拒绝。失败73停止，不改写系统代码。
- 绑定前核验原生source非空、runLoop为主循环、source实际加入common modes。
- 正确解码waitpid的信号/退出码。保留独立AX触摸源、真实UIControl自检、主App和所有对象/人设/加密记忆。

## 验证与限制

待macOS CI：16项生产匹配器检查、6项wait-status检查、原核心/记忆/OCR/长人设检查、独立HUD和四target设备编译、模拟器触摸对照、签名打包。本机Windows缺Apple SDK/plutil；工程已用原生成器生成，新增Shared文件纳入sources。

模拟器内部事件测试不代表iOS17.0/TrollStore全局显示、硬件触摸、键盘、跨App截屏/复制成功。本次有真实崩溃栈依据，仍待最终真机验收，不提前宣称修好。无真实API调用、消息发送或私人聊天上传。
