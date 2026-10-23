# TrollStore 个人构建

2026-10-23：为 iPhone 15 / iOS 17.0 增加独立的 GitHub Actions 真机打包流程。

- 工作流：`.github/workflows/ios-trollstore.yml`，手动运行 **Build TrollStore IPA**。
- 基于现有 Xcode 工程构建 Release / iphoneos / arm64，最低系统版本仍沿用工程的 iOS 16.0。
- 不需要 Apple 开发者账号、证书或描述文件。模型 API Key 安装后在手机填写，不写入构建文件。
- 保留主 App、键盘和实验截屏扩展；原有普通签名及模拟器流程不变。
- 主 App 与扩展使用原有 App Group，主 App 与键盘使用固定的个人构建共享钥匙串组。
- `tools/package_trollstore.py` 使用 Homebrew ldid 伪签名必要权限，不添加解除沙盒或平台权限。
- 打包前检查平台、架构、最低版本、三个 target 的共享组与权限；打包后检查 ZIP 完整性和可执行权限。
- 产物为 `GoutouJunshi-TrollStore.ipa`、SHA-256 和构建信息。Actions 下载的外层 ZIP 需要先解压。

验证状态：本机 Windows 可执行 Python 语法与打包前置条件检查；Swift 构建及上游检查需要云端 macOS。尚待完成云端构建与 iPhone 实机验证，不能把 IPA 打包成功当作键盘、共享钥匙串及快捷指令已实测。

不要随意改变 Bundle ID、App Group 或共享钥匙串组，以免更新后无法访问旧配置或 Key。通过 TrollStore 覆盖更新，保留原有数据。
