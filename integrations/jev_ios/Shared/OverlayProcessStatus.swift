import Foundation

enum OverlayProcessStatus {
    // waitpid returns an encoded wait status, not an exit code.
    static func describe(_ raw: Int32) -> String {
        let signal = raw & 0x7f
        if signal == 0 { return "退出码\((raw >> 8) & 0xff)" }
        if signal == 0x7f { return "进程已暂停（信号\((raw >> 8) & 0xff)）" }
        let name = signal == 11 ? "SIGSEGV，内存访问异常" : signal == 6 ? "SIGABRT，运行时终止" : "信号\(signal)"
        return "\(name)；原始状态\(raw)"
    }
}
