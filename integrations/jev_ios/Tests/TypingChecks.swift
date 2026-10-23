import Foundation

@main
struct TypingChecks {
    static var count = 0
    static func check(_ name: String, _ value: @autoclosure () -> Bool) {
        count += 1
        guard value() else { fputs("FAIL: \(name)\n", stderr); exit(1) }
    }
    static func main() throws {
        let path = CommandLine.arguments[1]
        let engine = PinyinEngine(tsv: try String(contentsOfFile: path, encoding: .utf8))
        check("Offline production vocabulary", engine.entryCount > 60_000)
        let text = try String(contentsOfFile: path, encoding: .utf8)
        let flypy = PinyinEngine(tsv: Flypy.dictionary(text))
        for (code, word) in [("nihc", "你好"), ("vsgo", "中国"), ("ui jm".replacingOccurrences(of: " ", with: ""), "时间"), ("xp xp".replacingOccurrences(of: " ", with: ""), "谢谢"), ("lv", "绿")] {
            check("Xiaohe \(code) contains \(word)", flypy.candidates(for: code).contains { $0.text == word && $0.consumed == code.count })
        }
        check("Xiaohe zero initials", Flypy.syllable("a") == "aa" && Flypy.syllable("ai") == "ai" && Flypy.syllable("ang") == "ah")
        check("Xiaohe compound initials", Flypy.syllable("shuang") == "ul" && Flypy.syllable("zhong") == "vs" && Flypy.syllable("chi") == "ii")
        for (code, word) in [("nihao", "你好"), ("wo", "我"), ("xiexie", "谢谢"), ("mingtian", "明天"),
                             ("zhoumo", "周末"), ("pengyou", "朋友"), ("shijian", "时间"), ("lv", "绿")] {
            check("\(code) contains \(word)", engine.candidates(for: code).contains { $0.text == word && $0.consumed == code.count })
        }
        check("Continuous multiword sentence", engine.candidates(for: "womingtiankanyoumeiyoushijian").contains { $0.text == "我明天看有没有时间" })
        check("Incomplete final syllable", engine.candidates(for: "niha").contains { $0.text == "你好" })
        check("Leading word remains selectable", engine.candidates(for: "nihaozzzz").contains { $0.text == "你好" && $0.consumed == 5 })
        check("Explicit syllable separator", engine.candidates(for: "xi'an").contains { $0.text == "西安" && $0.consumed == 5 })
        check("Separator prevents incorrect syllable merging", !engine.candidates(for: "xi'an").contains { $0.text == "先" })
        check("Trailing separator", engine.candidates(for: "nihao'").contains { $0.text == "你好" && $0.consumed == 6 })
        check("Empty input", engine.candidates(for: "").isEmpty)
        check("Unsupported input remains raw", engine.candidates(for: "qwerty9").isEmpty)
        check("Uppercase isn't misdecoded", engine.candidates(for: "ABC").isEmpty)
        check("Bounded composition", engine.candidates(for: String(repeating: "a", count: 65)).isEmpty)
        check("Bounded candidates", engine.candidates(for: "shi", limit: 3).count == 3)
        let choices = engine.candidates(for: "shi")
        check("No duplicate candidates", Set(choices.map { "\($0.text):\($0.consumed)" }).count == choices.count)
        var composition = PinyinComposition()
        check("Delete delegates to host when empty", !composition.backspace())
        composition.append("'")
        check("No leading separator", composition.raw.isEmpty)
        for char in "nihao" { composition.append(String(char)) }
        check("Preedit stores Pinyin without touching host", composition.raw == "nihao")
        check("Delete stays in preedit", composition.backspace() && composition.raw == "niha")
        composition.append("o")
        check("Selection produces selected text", composition.select(PinyinCandidate(text: "你好", consumed: 5)) == "你好")
        check("Selection consumes only matched Pinyin", composition.raw.isEmpty)
        for char in "nihao'ma" { composition.append(String(char)) }
        check("Partial word selection", composition.select(PinyinCandidate(text: "你好", consumed: 5)) == "你好" && composition.raw == "ma")
        check("Invalid stale length cannot consume", composition.select(PinyinCandidate(text: "错误", consumed: 99)) == nil && composition.raw == "ma")
        composition.clear(); composition.append("n"); composition.append("'"); composition.append("'")
        check("No repeated separator", composition.raw == "n'")
        composition.append("9"); composition.append("你")
        check("Only Pinyin keys append", composition.raw == "n'")
        composition.clear()
        for _ in 0..<100 { composition.append("n") }
        check("Pending Pinyin limited", composition.raw.count == 64)
        composition.clear()
        check("Switching documents clears preedit", composition.raw.isEmpty)
        let start = Date()
        for text in ["nihao", "womingtiankanyoumeiyoushijian", String(repeating: "a", count: 64)] {
            _ = engine.candidates(for: text)
        }
        print("PASS: \(count) offline typing checks; production lexicon \(engine.entryCount) entries; sample lookups \(Int(Date().timeIntervalSince(start) * 1000)) ms")
    }
}
