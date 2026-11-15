import SwiftUI
import UIKit

struct ReplyReviewView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    let original: String
    let objectID: String
    @State var text: String
    @State private var message = ""
    var body: some View {
        Form {
            Section("编辑回复") {
                TextEditor(text: $text).frame(minHeight: 150)
                Text("复制后到目标聊天粘贴；不会自动发送。复制不等于已发送。")
                    .font(.caption).foregroundStyle(Palette.secondary)
                Button("复制当前文字") {
                    guard !text.trimmed.isEmpty, text.count <= 1000 else { message = "回复请保留1–1000字"; return }
                    UIPasteboard.general.setItems([["public.utf8-plain-text":text]], options:[.localOnly:true])
                    message = "已复制，可切回任意聊天App粘贴"
                }.buttonStyle(BrandPrimaryButtonStyle())
            }
            Section("让下次更像我") {
                Button("记住这次修改") {
                    do {
                        guard model.relationship.id == objectID, let store = model.store, !model.demo else { throw GoutouError.invalid("对象已变化或当前是演示，请回到真实对象后重试") }
                        try store.memoryStore().saveStyle(objectID,original:original,approved:text)
                        message = "修改已加密保存，只用于此对象后续生成；未发送消息"
                    } catch { message = error.localizedDescription }
                }
                Text("需先开启此对象长期记忆。保存最近8组修改，比较句长、问句和标点并提供给后续回复参考；不是训练模型权重。可在记忆页清空。")
                    .font(.caption).foregroundStyle(Palette.secondary)
            }
            Text(message).font(.footnote).foregroundStyle(Palette.secondary).textSelection(.enabled)
        }.scrollContentBackground(.hidden).background(Palette.cream)
            .navigationTitle("审核并复制").modifier(FormKeyboardDismissal())
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("返回") { dismiss() } } }
    }
}
