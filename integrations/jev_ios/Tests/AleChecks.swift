import Foundation
@main struct AleChecks {
    static func main() throws {
        let old = Data(#"{"id":"old","label":"旧对象","stage":"伴侣","goal":"自然接话","background":"","notes":""}"#.utf8)
        var relationship = try JSONDecoder().decode(Relationship.self, from: old)
        precondition(relationship.coaching == nil)
        precondition(relationship.sourceApp == nil)
        relationship.sourceApp = "小红书"
        precondition(AlePresets.all.count == 18)
        for card in AlePresets.all {
            let stage = relationship.stage
            card.apply(to: &relationship)
            try relationship.validate()
            precondition(relationship.stage == stage)
            let restored = try JSONDecoder().decode(Relationship.self,from:JSONEncoder().encode(relationship))
            precondition(restored == relationship)
        }
        relationship.coaching?.nicknames = "只给这个对象"
        let other = Relationship()
        precondition(other.coaching == nil)
        let longPersona = String(repeating: "真实人设与说话习惯。", count: 5000)
        relationship.coaching?.persona = longPersona
        relationship.coaching?.expression = longPersona
        relationship.coaching?.avoid = longPersona
        try relationship.validate()
        let roundtrip = try JSONDecoder().decode(Relationship.self, from: JSONEncoder().encode(relationship))
        precondition(roundtrip.coaching?.persona == longPersona)
        precondition(roundtrip.coaching?.expression == longPersona)
        precondition(roundtrip.coaching?.avoid == longPersona)
        relationship.background = longPersona
        relationship.notes = longPersona
        try relationship.validate()
        let api = ModelAPI(transport: HTTPTransport(), config: AppConfig(), secrets: ProviderSecrets(deepseek: "offline-placeholder"))
        let payload = try GoutouPipeline(api: api).input(Transcript(text: "对方：今天好吗\n我：还不错", confirmed: true), relationship)
        let submitted = try ModelJSON.object(payload)
        let preferences = try ModelJSON.object(submitted["coaching"] as! String)
        precondition(preferences["persona"] as? String == longPersona)
        precondition(submitted["background"] as? String == longPersona)
        let session = AleOverlaySession(config: AppConfig(), people: [.init(relationship: relationship, rules: "offline")],
            selectedID: relationship.id, secrets: .init(), memoryKey: Data(repeating: 1, count: 32),
            containerPath: "/test", statusPath: "/test/status", mobileUID: 501, mobileGID: 501)
        try session.validate()
        let restoredSession = try JSONDecoder().decode(AleOverlaySession.self, from: JSONEncoder().encode(session))
        precondition(restoredSession.people[0].relationship.coaching?.persona == longPersona)
        print("PASS: Ale coaching legacy decode, 18 presets, stage preservation, full long-persona roundtrip, object isolation")
    }
}
