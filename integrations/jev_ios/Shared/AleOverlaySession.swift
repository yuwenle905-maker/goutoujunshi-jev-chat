import Foundation

/// Transferred only through an inherited anonymous pipe. Never log or write this
/// object to disk: it contains model credentials and the local archive key.
struct AleOverlaySession: Codable {
    struct Person: Codable {
        var relationship: Relationship
        var rules: String
    }
    var config: AppConfig
    var people: [Person]
    var selectedID: String
    var secrets: ProviderSecrets
    var memoryKey: Data
    var containerPath: String
    var statusPath: String
    var mobileUID: UInt32
    var mobileGID: UInt32
    func validate() throws {
        try config.validate()
        guard !people.isEmpty, people.count <= 100,
              Set(people.map { $0.relationship.id }).count == people.count,
              people.contains(where: { $0.relationship.id == selectedID }),
              memoryKey.count == 32, containerPath.hasPrefix("/"), statusPath.hasPrefix(containerPath + "/") else {
            throw GoutouError.invalid("悬浮会话资料无效，请回主App重新启动")
        }
        for person in people { try person.relationship.validate() }
    }
}
