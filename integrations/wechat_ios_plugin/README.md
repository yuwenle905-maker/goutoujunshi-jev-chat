# 狗头微信 AI 插件 0.1.1

目标设备：iOS 17.0 / 已安装 TrollStore / 微信 8.0.75。与原 Windows 助手、独立 iOS 键盘 App 分开维护。用户自行用注入器加载 `.dylib`；本项目不交付微信 IPA。

**状态：后端与插件通用层实现；8.0.75 私有收发接口尚未真机核验。构建默认关闭实发。编译成功不等于微信收发成功，不得将诊断动态库称为可用自动代聊成品。**


## 0.1.1 启动稳定性与闪退取证

- 用户反馈0.1.0经TrollFools注入微信8.0.75后闪退。收到的4份wakeups报告是10月21/23日资源记录，Action taken为none，早于本插件，无法认定此次崩溃原因。
- 构造器只记录C层启动标记并派发主队列任务，不在构造器调用Foundation/UIKit或安装Hook。App进入active后再延迟3秒安装公开三指长按入口，默认不挂消息/导航Hook。
- 本诊断版每次启动将enabled/automatic关闭；三指长按打开面板，用户打开总开关后才安装消息与导航Hook。重复开启有幂等保护。实发仍关闭，不能靠打开总开关绕过。
- Objective-C类统一使用GTWXAI前缀、C符号默认隐藏；不宣称已发现类冲突，静态检查未在两个用户提供deb中找到旧GT类名字符串。
- 启动日志同步写入容器Library/Logs/GoutouAI-boot.log，并向系统控制台输出GoutouWechatAI标记；仅固定事件码，不含聊天/密钥，0600权限，超过32KiB截断。面板可复制/清空，上次启动的日志不再因进程退出丢失。若在dyld加载前就被终止，仍必须查看系统.ips。
- 附GoutouLoadProbe.dylib是独立C层加载探针，无ObjC/UI/消息Hook/网络。它不是代聊程序。对比时先在TrollFools只移除旧GoutouAI，再选其中一份注入；不要把探针和主库同时注入。不要卸载微信或清聊天。
- 新增macOS启动日志单测和合成UIKit模拟器宿主：验证延迟启动、公开入口、明确开启后才Hook、重复开启及原回调保留。模拟器不是微信8.0.75真机，不能据此声称修复了真机闪退。

## 1. 架构与难点

```text
微信进程 → 版本适配器 → 当前账号/会话独立队列 → HTTPS 后端 → DeepSeek
                        ↑修订号校验、人工审核← JSON 回复校验 ←
                        → 已验证发送适配器 → 回执/未知结果熔断
```

后端不连接微信、不操作手机。手机只上传当前对象上下文、人设和少量人工样本。各关系独立保存阶段、目标、状态、边界；本人回复使旧任务作废，之后的新来信继续处理。API 有鉴权、限流、五分钟幂等响应缓存；内存缓存包含短期请求指纹和回复，不落盘。重启会清空。后端缓存不是发送去重账本；发送账本在手机持久化。

TrollStore 是 IPA 安装工具，不是通用注入引擎。现有微信私有方法名只作为候选适配层。运行时签名检查能减少不匹配调用，不能证明语义正确。iOS 会挂起后台 App；插件不能保证锁屏、进程被杀时一直执行，也没有静音音频保活。

## 2. 后端先运行

需要 Node 22+，无 npm 外部依赖。

```sh
cp .env.example .env
# 编辑随机 DEVICE_TOKEN、DEEPSEEK_API_KEY；密钥不提交 Git
npm test
npm start
```

Node 默认仅监听 127.0.0.1:8787，公网用 Caddy 等反代提供 HTTPS。参考 `backend/Caddyfile`。Docker 示例：`docker build -f backend/Dockerfile -t goutou-ai .`；运行时用 `--env-file .env -p 127.0.0.1:8787:8787`。服务进程一份、个人使用，非多租户服务。DEVICE_TOKEN 要足够随机，泄露后需更换，不能用用户名代替。

接口：`GET /health` 存活检查；`GET /v1/models` 鉴权模型列表；`POST /v1/reply` 生成。后两者使用 `Authorization: Bearer <DEVICE_TOKEN>`。可选 `X-DeepSeek-Key` 覆盖服务器密钥，仅供你信任的后端；建议统一在服务器配置。后端只向固定 DeepSeek 官方域名请求，不接受任意供应商地址和远程图片 URL。

请求示例见 `docs/request.json`。history 最多40条、examples 最多6组，账号与会话独立；history 是调用方提供的近期上下文，本版本不读取或导入整套旧微信数据库。长期原始聊天不在云端持久化，不把 PC 的 DPAPI 数据库复制到 Linux 冒充可解密。

默认温度0.9，可在手机配置0–2，非思考模式。高温度不保证更像真人。严格禁客服用词、避免惯性反问、尊重对方表达偏好、不捏造近况、不主动邀请电话/视频。正向风格样本只来自用户维护的人工样本与明确修改；不是模型权重训练。未通过反官方校验会强制审核，不自动发送。

图片使用真实 `image_url` 数据块并明确路由到 `deepseek-flash`；最多2张，每张1MiB，支持实际格式匹配的 JPEG/PNG/GIF/WebP。动态表情的动画语义不保证完整理解。没有获取到媒体字节时不能把 `[图片]` 当成已识别。iOS 自动获取媒体缓存路径仍需8.0.75真机适配，当前候选接收层仅处理文字，不伪造图片识别成功。

## 3. iOS 插件逻辑

`GTAdapter.m` 是唯一私有接口边界；`GTCoordinator.m` 管理消息去重、跨对象任务、过期回复作废、审核、发送账本、频率限制和未知结果熔断；`GTConfig.m` 提供 NSURLSession、Keychain 和原子写入。

候选接收：`CMessageMgr/AsyncOnAddMsg:MsgWrap:`；候选发送：`AddMsg:MsgWrap:`。这些来自历史公开插件，不代表8.0.75实测。`GT_VERIFIED_8075_SEND` 默认0，界面和日志明确“不开放实发”。不得只改宏就宣传适配完成。需要真机验证字段、身份、收发事件、账号切换、离线同步、重复事件与回执后再开放。

默认总开关、云端许可、自动发送、所有好友、群聊均关闭。仅当前对象开关/全部好友开关才纳入处理；群聊需明确开关，未适配结构化@时仅“免@”显式开启才处理。模板 JSON 与分析文字不会作为聊天正文发送。

自动模式在前台展示五秒无操作确认，修改停止倒计时。无法展示审核弹窗时保留草稿，不暗中视作用户已经看见。真正后台处理依赖微信进程当前有执行时间及版本适配；本版未验收。分条回复协议支持1–2条，但第二条暂留，需补全真实回执适配后启用，避免无确认连发。

“账号保护”包括默认白名单、15秒全局最小间隔、每日50条、消息幂等、旧任务作废、未知结果熔断；不规避微信风控、不保证防封。恢复按钮只解除当前关系熔断，不自动重发旧消息。发送方法返回或本地回显均不能证明对方已收到。

Keychain 保存令牌和可选 Key；配置文件使用 iOS Complete Data Protection + 原子写入，未另加独立应用层加密。锁屏时可能不可读。近期聊天只在内存；人设、人工样本与发送指纹持久化于微信容器下独立 `GoutouAI` 子目录，清理或换包前注意备份。诊断仅最近200条事件码，无正文、Key、联系人ID，不上传。

## 4. UI 与 dylib 打包

UIKit 原生现代卡片、材质 Banner，AI 配置 / 此段关系 / 回复审核 / 可清空日志四入口。设置页和聊天页候选导航栏添加 AI 按钮，保留原有按钮。微信页面类名或 `GetContact` 更改时会记录诊断并拒绝猜联系人；需要真机核验入口。
如果版本私有页面入口不匹配，三指长按微信界面1秒也可通过公开 UIKit 手势打开配置与诊断，不依赖微信页面类名。

macOS + Xcode iPhoneOS SDK：

```sh
bash scripts/build-ios.sh
# 输出 build/GoutouAI.dylib（iOS17 arm64）和 SHA256SUMS.txt
```

无 CydiaSubstrate、Logos、Swift 运行时依赖。CI 使用 macOS 执行同一脚本，做编译、Mach-O依赖及 ad-hoc 签名校验，**不等价真机验收**。`.dylib` 不是 `.dilly`。你使用的注入器需要支持 arm64 iOS17和目标微信包：将动态库嵌入目标 App 并添加加载命令，重新签名宿主及嵌入动态库，再经 TrollStore 安装。只签动态库不足以改变原 App Store 微信。不要直接覆盖唯一在用的微信数据；不分发或上传微信安装包。

如用 Mac 手工注入，`insert_dylib` 官方用法为：

```sh
insert_dylib --all-yes --inplace '@executable_path/Frameworks/GoutouAI.dylib' /path/to/copied/Payload/WeChat.app/WeChat
```

前提是已把库放进上述 Frameworks，且是你有权处理的、可修改的副本；最终签名/IPA由你的注入器完成。上面命令本身不解密安装包、不完成 TrollStore 打包，不提供“任何版本一定成功”的保证。

## 5. 验收

测试合成 API 输入、幂等、关系隔离、格式/禁词、视觉请求构造、鉴权和脱敏日志；不使用私人聊天、不消耗真实模型、不发微信。真机待验收清单见 `docs/DEVICE_ACCEPTANCE.md`。本任务不影响原有 Windows 数据、键盘 App 与其它平台代码。

参考原始资料：[TrollStore](https://github.com/opa334/TrollStore)、[DeepSeek 聊天 API](https://api-docs.deepseek.com/api/create-chat-completion/)、[视觉 API](https://api-docs.deepseek.com/guides/vision/)、[Apple 后台执行](https://developer.apple.com/documentation/uikit/about-the-background-execution-sequence)、[历史 Hook 示例](https://github.com/NotAfraidLTD/Tweak/blob/master/Tweak.xm)、[insert_dylib](https://github.com/Tyilo/insert_dylib)。
