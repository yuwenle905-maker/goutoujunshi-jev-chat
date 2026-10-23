import Foundation

/// Xiaohe double-Pinyin sound codes, without Flypy shape/auxiliary codes.
/// Uses the existing licensed offline vocabulary, not a network input service.
enum Flypy {
    static let finals = ["iu":"q", "ei":"w", "uan":"r", "ue":"t", "ve":"t", "un":"y",
                         "uo":"o", "ie":"p", "ong":"s", "iong":"s", "ing":"k", "uai":"k",
                         "ai":"d", "en":"f", "eng":"g", "iang":"l", "uang":"l", "ang":"h",
                         "ian":"m", "an":"j", "ou":"z", "ia":"x", "ua":"x", "iao":"n",
                         "ao":"c", "ui":"v", "in":"b", "a":"a", "o":"o", "e":"e", "i":"i", "u":"u", "v":"v"]
    static func syllable(_ value: String) -> String? {
        if ["a", "o", "e"].contains(value) { return value + value }
        if ["ang":"ah", "eng":"eg", "ong":"os"][value] != nil { return ["ang":"ah", "eng":"eg", "ong":"os"][value] }
        if let first = value.first, "aoe".contains(first), value.count == 2 { return value }
        let initial: String, rest: String
        if let pair = ["zh":"v", "ch":"i", "sh":"u"].first(where: { value.hasPrefix($0.key) }) {
            initial = pair.value; rest = String(value.dropFirst(2))
        } else {
            guard let first = value.first else { return nil }
            initial = String(first); rest = String(value.dropFirst())
        }
        guard let final = finals[rest] else { return nil }
        return initial + final
    }
    static func dictionary(_ tsv: String) -> String {
        tsv.split(separator: "\n").compactMap { line -> String? in
            let parts = line.split(separator: "\t", omittingEmptySubsequences: false)
            guard parts.count >= 4, !line.hasPrefix("#") else { return nil }
            let syllables = parts[3].split(separator: "'").map(String.init)
            let codes = syllables.compactMap(syllable)
            guard codes.count == syllables.count else { return nil }
            return codes.joined() + "\t" + parts[1] + "\t" + parts[2] + "\t" + codes.joined(separator: "'")
        }.joined(separator: "\n")
    }
}
