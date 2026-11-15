import SwiftUI
import CryptoKit
import Darwin

@_silgen_name("posix_spawnattr_set_persona_np")
private func persona(_ attr: UnsafePointer<posix_spawnattr_t?>, _ id: uid_t, _ flags: UInt32) -> Int32
@_silgen_name("posix_spawnattr_set_persona_uid_np")
private func personaUID(_ attr: UnsafePointer<posix_spawnattr_t?>, _ id: uid_t) -> Int32
@_silgen_name("posix_spawnattr_set_persona_gid_np")
private func personaGID(_ attr: UnsafePointer<posix_spawnattr_t?>, _ id: gid_t) -> Int32

@MainActor final class OverlayCoordinator: ObservableObject {
    static let shared = OverlayCoordinator()
    @Published var status = "未启动跨App悬浮窗"
    @Published var busy = false
    func stop() {
        CFNotificationCenterPostNotification(CFNotificationCenterGetDarwinNotifyCenter(),
            CFNotificationName("ai.ale.assistant.hud.stop" as CFString), nil, nil, true)
        status = "已请求关闭悬浮窗"
    }
    func start(_ store: GoutouStore?) {
        guard !busy else { return }
        do {
            #if targetEnvironment(simulator)
            throw GoutouError.invalid("系统级悬浮需要TrollStore真机；模拟器仅验证面板组件")
            #else
            guard let store = store,
                  let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: GoutouStore.group) else {
                throw GoutouError.invalid("未找到共享资料，请检查TrollStore安装")
            }
            let helper = Bundle.main.bundleURL.appendingPathComponent("AleHUD").path
            guard FileManager.default.isExecutableFile(atPath: helper) else { throw GoutouError.invalid("安装包缺少悬浮进程，请安装完整IPA") }
            let current = store.relationship()
            let profiles = [current] + store.archived().filter { $0.id != current.id }
            let people = try profiles.map { p in AleOverlaySession.Person(relationship: p,
                rules: try store.skillRules.current().context(goal: p.goal, background: p.background + "\n" + p.notes, transcript: "")) }
            // Precreate all snapshot profiles' mobile-owned lock files before root startup.
            for profile in profiles { _ = try store.memoryStore().load(profile.id) }
            let statusURL = container.appendingPathComponent("AleHUDStatus-" + UUID().uuidString + ".json")
            let snapshot = AleOverlaySession(config: store.config(), people: people, selectedID: current.id,
                secrets: try CredentialVault.load(), memoryKey: try MemoryEncryptionKey.load().withUnsafeBytes { Data($0) },
                containerPath: container.path, statusPath: statusURL.path, mobileUID: getuid(), mobileGID: getgid())
            try snapshot.validate()
            let data = try JSONEncoder().encode(snapshot)
            stop(); busy = true; status = "正在启动独立悬浮进程…"
            DispatchQueue.global(qos: .userInitiated).async {
                let result = Self.launch(helper: helper, payload: data, statusURL: statusURL)
                Task { @MainActor in self.busy = false; self.status = result }
            }
            #endif
        } catch { status = error.localizedDescription }
    }
    nonisolated private static func launch(helper: String, payload: Data, statusURL: URL) -> String {
        Thread.sleep(forTimeInterval: 0.3)
        var fds: [Int32] = [0, 0]
        guard pipe(&fds) == 0 else { return "启动失败：无法创建本机会话管道" }
        _ = fcntl(fds[0], F_SETFD, FD_CLOEXEC); _ = fcntl(fds[1], F_SETFD, FD_CLOEXEC)
        _ = fcntl(fds[1], F_SETNOSIGPIPE, 1)
        var attr: posix_spawnattr_t?, actions: posix_spawn_file_actions_t?
        posix_spawnattr_init(&attr); posix_spawn_file_actions_init(&actions)
        defer { posix_spawnattr_destroy(&attr); posix_spawn_file_actions_destroy(&actions) }
        guard persona(&attr, 99, 1) == 0, personaUID(&attr, 0) == 0, personaGID(&attr, 0) == 0 else {
            close(fds[0]); close(fds[1]); return "无法获得HUD启动权限，请使用TrollStore安装"
        }
        posix_spawn_file_actions_adddup2(&actions, fds[0], STDIN_FILENO)
        posix_spawn_file_actions_addclose(&actions, fds[0]); posix_spawn_file_actions_addclose(&actions, fds[1])
        var pid: pid_t = 0
        let args = [strdup(helper), strdup("--hud"), nil]
        let environment = [strdup("PATH=/usr/bin:/bin:/usr/sbin:/sbin"), nil]
        defer { for p in args { if let p = p { free(p) } } }
        defer { for p in environment { if let p = p { free(p) } } }
        let code = args.withUnsafeBufferPointer { argv in
            environment.withUnsafeBufferPointer { envp in
                posix_spawn(&pid, helper, &actions, &attr, UnsafeMutablePointer(mutating: argv.baseAddress!),
                    UnsafeMutablePointer(mutating: envp.baseAddress!))
            }
        }
        close(fds[0])
        guard code == 0 else { close(fds[1]); return "悬浮进程启动失败（\(code)），请确认TrollStore权限" }
        var sent = 0
        payload.withUnsafeBytes { raw in
            while sent < raw.count {
                let n = write(fds[1], raw.baseAddress!.advanced(by: sent), raw.count - sent)
                if n < 0 && errno == EINTR { continue }
                if n <= 0 { break }; sent += n
            }
        }
        close(fds[1])
        for _ in 0..<100 {
            if let data = try? Data(contentsOf: statusURL),
               let item = try? JSONSerialization.jsonObject(with: data) as? [String: String], let message = item["message"] {
                try? FileManager.default.removeItem(at: statusURL)
                // Reap this child asynchronously when the user closes its HUD.
                DispatchQueue.global(qos: .utility).async { var result: Int32 = 0; _ = waitpid(pid, &result, 0) }
                return message
            }
            var code: Int32 = 0
            if waitpid(pid, &code, WNOHANG) == pid { return "悬浮进程未完成启动（\(OverlayProcessStatus.describe(code))）；主App仍可使用" }
            Thread.sleep(forTimeInterval: 0.1)
        }
        CFNotificationCenterPostNotification(CFNotificationCenterGetDarwinNotifyCenter(), CFNotificationName("ai.ale.assistant.hud.stop" as CFString), nil, nil, true)
        return "悬浮进程启动超时，已请求停止；请检查TrollStore安装与系统版本"
    }
}

struct OverlaySettingsSection: View {
    @EnvironmentObject var model: AppModel
    @ObservedObject private var overlay = OverlayCoordinator.shared
    var body: some View {
        Section("跨 App 悬浮窗 · TrollStore") {
            Button("开启／刷新悬浮窗") { overlay.start(model.store) }.disabled(overlay.busy)
            Button("关闭悬浮窗") { overlay.stop() }
            Text(overlay.status).font(.footnote)
            Text("回到微信、抖音等App后点击悬浮球。先选对象，再截取当前屏幕或读取剪贴板，核对后生成、复制。修改对象、人设或接口设置后，保存并点此刷新；不自动监听或发送。跨App权限需在你的iOS17.0真机验收。")
                .font(.caption).foregroundStyle(Palette.secondary)
        }
    }
}
