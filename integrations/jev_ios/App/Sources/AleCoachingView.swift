import SwiftUI

struct AleCoachingSection: View {
    @Binding var relationship: Relationship
    @State private var preset = "自定义"
    private func field(_ path: WritableKeyPath<CoachingPreferences,String>) -> Binding<String> {
        Binding(get: { (relationship.coaching ?? CoachingPreferences())[keyPath:path] }, set: { value in
            var p = relationship.coaching ?? CoachingPreferences(); p[keyPath:path] = value; relationship.coaching = p
        })
    }
    var body: some View {
        Section("关系策略与我的表达") {
            Picker("策略预设", selection: $preset) {
                Text("自定义").tag("自定义")
                ForEach(AlePresets.all) { Text($0.name).tag($0.name) }
            }
            if let card = AlePresets.all.first(where: { $0.name == preset }) {
                Text(card.guide).font(.footnote).foregroundStyle(Palette.secondary)
                Button("应用此策略") { card.apply(to: &relationship) }
                Text("会调整目标、人设和表达方式；保留实际关系阶段、昵称和你的自定义限制。保存对象后生效。")
                    .font(.caption).foregroundStyle(Palette.secondary)
            }
            TextField("我的人设与性格", text: field(\.persona), axis: .vertical).lineLimit(2...5)
            TextField("表达风格，例如松弛幽默、温柔直球", text: field(\.tone))
            TextField("推进方式，例如自然回应、轻度试探", text: field(\.progression))
            TextField("双方投入，例如我主动更多", text: field(\.investment))
            TextField("昵称偏好，例如宝宝、名字或不用昵称", text: field(\.nicknames))
            TextField("亲密表达偏好，例如撒娇、直球、日常拌嘴", text: field(\.expression), axis: .vertical).lineLimit(2...4)
            TextField("避免的表达，例如连续反问、主动邀约", text: field(\.avoid), axis: .vertical).lineLimit(2...4)
        }.onAppear { preset = relationship.coaching?.preset ?? "自定义" }
            .onChange(of: relationship.id) { _ in preset = relationship.coaching?.preset ?? "自定义" }
    }
}
