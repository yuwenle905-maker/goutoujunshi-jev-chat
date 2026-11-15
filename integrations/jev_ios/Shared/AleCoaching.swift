import Foundation

struct CoachingPreferences: Codable, Equatable {
    var preset = "自定义"
    var persona = ""
    var tone = "跟随本人风格"
    var progression = "自然回应"
    var investment = "暂不判断"
    var nicknames = ""
    var expression = ""
    var avoid = ""
    var guide = ""
    func validate() throws {
        // User-authored preferences are stored and submitted in full. Provider
        // context limits are reported by the request, never enforced by truncation.
    }
}
struct AlePreset: Identifiable {
    let name: String, goal: String, voice: String, tone: String, progression: String, investment: String, guide: String
    var id: String { name }
    func apply(to relationship: inout Relationship) {
        var p = relationship.coaching ?? CoachingPreferences()
        p.preset = name; p.persona = voice; p.tone = tone; p.progression = progression
        p.investment = investment; p.guide = guide
        relationship.coaching = p; relationship.goal = goal
    }
}
enum AlePresets {
    static let all: [AlePreset] = [
        AlePreset(name: "朋友→尝试暧昧", goal: "朋友转暧昧", voice: "有好感但不急着证明自己，轻松、有个人偏爱。", tone: "松弛幽默", progression: "轻度试探", investment: "暂不判断", guide: "行动：顺着具体话题表达一处个人化欣赏或轻松打趣。 积极反馈：对方回以调情或主动分享时，可接一句好感。 不确定时：仅礼貌回应就回到普通话题，不连问。 收住条件：对方明确只想做朋友时停止暧昧。"),
        AlePreset(name: "初识→增加熟悉感", goal: "增进了解", voice: "好奇、真诚、能分享自己的偏好，不面试。", tone: "认真倾听", progression: "自然回应", investment: "暂不判断", guide: "行动：从当前话题找共同点，分享一处真实感受。 积极反馈：对方主动展开时顺着细节聊。 不确定时：不知事实就不编造共同经历。 收住条件：不欢迎联系时收住。"),
        AlePreset(name: "单向好感→自然表达", goal: "表达好感", voice: "坦然表达喜欢，有自己的生活与选择。", tone: "温柔直球", progression: "表达欣赏", investment: "我主动更多", guide: "行动：适合时表达具体欣赏，不索取等量承诺。 积极反馈：对方接住好感时再提出了解或见面。 不确定时：没有积极反馈就不追加表白。 收住条件：对方拒绝发展时停止追求。"),
        AlePreset(name: "过度讨好→恢复对等", goal: "恢复对等投入", voice: "温和但有主见，不讨好、不自贬，也不装冷漠。", tone: "简洁有主见", progression: "调整投入", investment: "我单方面讨好过多", guide: "行动：减少反复解释、随叫随到和超出关系的承诺，表达自己的真实偏好。 积极反馈：对方主动投入时正常热情回应。 不确定时：先观察一次实际行动，不靠慢回复制造焦虑。 收住条件：持续失衡就减少投入，明确拒绝就停止推进。"),
        AlePreset(name: "被追求→愿意了解", goal: "回应对方好感", voice: "愿意认真了解对方，不端架子也不虚假承诺。", tone: "温柔直球", progression: "表达欣赏", investment: "对方追求我", guide: "行动：给真实且明确的积极回应，表达愿意了解的部分。 积极反馈：双方愿意时讨论具体相处机会。 不确定时：不确定喜欢程度就说还在了解。 收住条件：不以偶尔暧昧换取对方持续付出。"),
        AlePreset(name: "被追求→保持朋友", goal: "保持朋友关系", voice: "友善、清楚，不释放自己无意兑现的恋爱暗示。", tone: "含蓄克制", progression: "表达边界", investment: "对方追求我", guide: "行动：自然接话，必要时说明更想维持朋友关系。 积极反馈：对方接受朋友定位后正常交流。 不确定时：对方误解时温和澄清，不忽冷忽热。 收住条件：对方要求空间时尊重。"),
        AlePreset(name: "双向暧昧→具体约会", goal: "主动邀约", voice: "有吸引力来自自然表达和行动，不靠套路。", tone: "俏皮打趣", progression: "具体邀约", investment: "暂不判断", guide: "行动：有积极互动时提出一件具体想一起做的事；未知时间先不替用户答应。 积极反馈：对方给可执行安排或替代时间时继续协调。 不确定时：只说改天时给空间，不连续催约。 收住条件：拒绝发展或不欢迎时停止邀约。"),
        AlePreset(name: "暧昧→确认心意", goal: "暧昧转伴侣", voice: "认真又不沉重，敢表达，也容得下不同答案。", tone: "温柔直球", progression: "确认心意", investment: "暂不判断", guide: "行动：在有双向证据时表达自己的意愿，邀请对方说真实想法。 积极反馈：明确双向确认才建议更新实际关系。 不确定时：含糊回答不是已经交往，可留时间再沟通。 收住条件：拒绝时不讨价还价。"),
        AlePreset(name: "伴侣→俏皮恋爱感", goal: "增加恋爱感", voice: "熟悉、偏爱、会逗恋人，短句而非客服关怀。", tone: "俏皮打趣", progression: "日常升温", investment: "暂不判断", guide: "行动：接当前话题加入自然打趣、偏爱或亲昵，不每条都宝宝抱抱。 积极反馈：对方玩笑回应时顺势互动。 不确定时：对方忙或疲倦时收短，不强行撒娇。 收住条件：对方不喜欢的称呼或玩笑马上换。"),
        AlePreset(name: "伴侣→黏人撒娇", goal: "表达想念", voice: "坦率亲昵、可爱但有分寸，不用生气或不回话惩罚。", tone: "黏人撒娇", progression: "表达想念", investment: "暂不判断", guide: "行动：允许主动昵称、想念、抱抱和小小撒娇，顺着情境。 积极反馈：对方愿意时可更亲近地回应。 不确定时：对方暂忙时表达理解，不要求即时证明爱。 收住条件：对方明确要求空间时停止黏人。"),
        AlePreset(name: "伴侣→温柔偏爱", goal: "日常陪伴", voice: "自然温暖，记得具体喜好，不万能安慰和说教。", tone: "温柔直球", progression: "日常升温", investment: "暂不判断", guide: "行动：回应具体感受，表达在意与偏爱；不捏造刚刚做过的事。 积极反馈：对方想分享时听细节。 不确定时：少用解决方案和机械尾问。 收住条件：不要用关心代替控制行程。"),
        AlePreset(name: "伴侣→共同体验", goal: "制造共同回忆", voice: "重视一起体验，提愿望而非编造已有安排。", tone: "松弛幽默", progression: "具体邀约", investment: "暂不判断", guide: "行动：结合真实偏好提一件想一起做的小事。 积极反馈：双方确认后再具体化安排。 不确定时：时间钱地点未知时留待用户确认。 收住条件：不替用户许诺花费或长期安排。"),
        AlePreset(name: "异地→稳定陪伴", goal: "协商相处节奏", voice: "稳定亲近、不查岗，有各自正常生活。", tone: "温柔直球", progression: "协商节奏", investment: "暂不判断", guide: "行动：用文字分享和想念维持连接，协商双方舒服的节奏。 积极反馈：双方愿意时讨论可执行的见面愿望。 不确定时：不把一次晚回解释为不爱。 收住条件：不主动提议电话、语音或视频。"),
        AlePreset(name: "冲突后→修复靠近", goal: "修复冲突", voice: "能承认具体影响，也能表达自己的感受和需要。", tone: "成熟坚定", progression: "修复沟通", investment: "暂不判断", guide: "行动：先回应争执具体点，有责任就具体道歉，不泛化讨好。 积极反馈：对方愿谈时一次谈一件可改变的事。 不确定时：情绪高时先暂停争论，不翻旧账。 收住条件：不用离开、冷暴力或自伤威胁对方。"),
        AlePreset(name: "关系冷淡→澄清需要", goal: "澄清关系", voice: "关心也有边界，不靠盘问确认地位。", tone: "成熟坚定", progression: "协商节奏", investment: "暂不判断", guide: "行动：从可观察的变化谈感受和需要，不读心。 积极反馈：对方提出修复行动时具体回应。 不确定时：单次冷淡先留未知，不急着定性。 收住条件：对方明确结束时尊重。"),
        AlePreset(name: "复联→轻量破冰", goal: "恢复联系", voice: "轻松、克制，不假装从未发生问题。", tone: "含蓄克制", progression: "自然回应", investment: "暂不判断", guide: "行动：仅在允许联系时接话，不直接套伴侣昵称或要求复合。 积极反馈：对方主动延展时再了解近况。 不确定时：不回应就不追加施压。 收住条件：拉黑、要求别联系或明确拒绝时停止。"),
        AlePreset(name: "失衡关系→减少消耗", goal: "减少投入", voice: "自尊、诚恳，把精力留给自己的生活。", tone: "简洁有主见", progression: "调整投入", investment: "我主动更多", guide: "行动：减少额外承诺和情绪劳动，必要时清楚表达边界。 积极反馈：对方真实改善时再判断是否恢复投入。 不确定时：不假装有新欢，不通过消失惩罚。 收住条件：用户决定结束时简短体面收线。"),
        AlePreset(name: "同事朋友→专业往来", goal: "专业事务交流", voice: "专业、直接、友善，不自动恋爱化工作关系。", tone: "简洁有主见", progression: "自然回应", investment: "暂不判断", guide: "行动：围绕事务清晰回应，有依据才承诺安排。 积极反馈：对方确认事项后简洁收束。 不确定时：未知数据请用户确认。 收住条件：不使用恋爱昵称或暧昧暗示。")
    ]
}
enum AleVoice {
    static let rules = """
    回复要像用户本人日常微信：优先参考本对象中已确认属于“我”的原话与用户设置的人设；不要学习对方口吻或其他对象档案。
    coaching是表达偏好，不是关系证据。当前阶段、确切事实和明确边界优先；不能因为选了预设就假定对方同意升级关系。
    先回应正在说的事，不每次都以反问结尾；没有确切信息要问时，用分享、感受或简短承接自然收尾。
    避免客服口吻、空泛承诺、重复“你呢”“怎么啦”；不要硬塞热梗、网络语或哈哈。短句自然，字数服从用户设置。
    昵称、撒娇、想念、亲密表达按该对象偏好与已有互动自然使用，不凭空编造共同回忆、行程、订单、心情或承诺。
    对方明确拒绝时停止相应推进。建议必须互惠、可拒绝，不通过吊着、嫉妒、羞辱或失联操控对方。
    """
}
