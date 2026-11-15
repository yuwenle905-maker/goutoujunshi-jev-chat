import Foundation
@main struct AleChecks {
    static func main() throws {
        let old = Data(#"{"id":"old","label":"旧对象","stage":"伴侣","goal":"自然接话","background":"","notes":""}"#.utf8)
        var relationship = try JSONDecoder().decode(Relationship.self, from: old)
        precondition(relationship.coaching == nil)
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
        relationship.coaching?.persona = String(repeating:"a",count:1601)
        do { try relationship.validate(); fatalError("Oversized persona accepted") } catch {}
        print("PASS: Ale coaching legacy decode, 18 presets, stage preservation, roundtrip, object isolation, limits")
    }
}
