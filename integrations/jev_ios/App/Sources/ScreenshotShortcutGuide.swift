import SwiftUI

struct ScreenshotShortcutGuide: View {
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(alignment: .leading, spacing: 10) {
                        Label("截屏后，文字直接回键盘", systemImage: "viewfinder").font(.title2.bold())
                        Text("在聊天中切换到狗头军师键盘，点顶部“识图”，再双击系统悬浮球运行截图快捷指令。识别完成后留在聊天页核对文字。")
                        Text("识图方式沿用配置页：Apple Vision 在本机识别；DeepSeek 或 OpenRouter 先在键盘显示截图预览，点“发送截图并识别”后上传。分析前仍需核对双方发言。只读取键盘上方的聊天区域。")
                            .font(.callout).foregroundStyle(Palette.secondary)
                    }.card()
                    VStack(alignment: .leading, spacing: 14) {
                        Text("先创建快捷指令").font(.headline)
                        step("1", "打开“快捷指令”，新建“截图问军师”。")
                        step("2", "添加系统的“截屏”操作（也可能显示为“拍摄截屏”）。")
                        step("3", "再添加狗头军师的“截图交给键盘（按配置）”，把“聊天截图”设为上一项的截屏结果。已有“截图交给键盘（本地）”动作会沿用新配置，无需重建。")
                        step("4", "保存。保持“截屏 → 截图交给键盘（按配置）”，使用时在键盘点“识图”→“收起键盘后截屏”，90 秒内触发截图；完成后点聊天输入框回来核对。")
                        Button("打开快捷指令") {
                            if let url = URL(string: "shortcuts://") { UIApplication.shared.open(url) }
                        }.buttonStyle(BrandPrimaryButtonStyle())
                    }.card()
                    VStack(alignment: .leading, spacing: 14) {
                        Text("放到系统悬浮按钮上").font(.headline)
                        Text("设置 → 辅助功能 → 触控 → 辅助触控。由你开启后，在“自定操作”中选择轻点两下或长按，再选择“截图问军师”。")
                        Text("也可到“触控 → 轻点背面”，把轻点两下或三下设为同一个快捷指令。支持的系统版本还可在控制中心添加“快捷指令”控件。")
                            .font(.callout).foregroundStyle(Palette.secondary)
                    }.card()
                    VStack(alignment: .leading, spacing: 10) {
                        Text("也可把截图交给主 App").font(.headline)
                        Text("若你想在主 App 核对原文，第二步选“识别聊天截图（按配置）”。它会打开主 App，并按设置进行本地识别或请求云端上传确认。")
                    }.card()
                    Text("首次运行时按系统提示允许这次操作。键盘本身无法直接触发其他 App 的系统截屏。顶部“识图”准备接收截图，真正的截屏由系统快捷指令完成。")
                        .font(.footnote).foregroundStyle(Palette.secondary)
                }.padding()
            }.background(Palette.cream).navigationTitle("一键截屏识别")
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
    }
    private func step(_ number: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(number).font(.callout.bold()).foregroundStyle(Palette.accent)
                .frame(width: 26, height: 26).background(Palette.highlight).clipShape(Circle())
            Text(text).frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
