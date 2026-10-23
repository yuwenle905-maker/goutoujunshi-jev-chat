import Foundation
import CryptoKit
import zlib

enum ChatImport {
    static let maximum = 1_000_000
    static func text(_ data: Data, filename: String) throws -> String {
        guard data.count <= 8_000_000 else { throw GoutouError.invalid("导入文件最多 8 MB") }
        let ext = (filename as NSString).pathExtension.lowercased()
        if ext == "zip" {
            let files = try zipTextFiles(data)
            guard files.count == 1 else { throw GoutouError.invalid("ZIP 中需恰有一份 TXT/CSV/JSON 聊天正文；多份时请解压后分别导入，避免混淆对象或顺序") }
            return try text(files[0].1, filename: files[0].0)
        }
        guard ["txt", "csv", "json", ""].contains(ext), data.count <= maximum else { throw GoutouError.invalid("支持 1 MB 内的 TXT、CSV、JSON，或含一份正文的 ZIP") }
        guard var raw = String(data: data, encoding: .utf8) ?? (data.starts(with: [0xff, 0xfe]) || data.starts(with: [0xfe, 0xff]) ? String(data: data, encoding: .utf16) : nil) else {
            throw GoutouError.invalid("文件不是 UTF-8 / UTF-16 文本，请转换编码后导入")
        }
        if raw.hasPrefix("\u{FEFF}") { raw.removeFirst() }
        if ext == "csv" {
            let rows = try ChatCSV.records(raw)
            guard let header = rows.first, let sender = header.firstIndex(of: "sender"), let message = header.firstIndex(of: "message") else {
                throw GoutouError.invalid("CSV 需要 sender,message 列，可另含 timestamp；sender 用 me/other 或 我/对方")
            }
            let time = header.firstIndex(of: "timestamp")
            raw = try rows.dropFirst().map { row in
                guard row.count == header.count else { throw GoutouError.invalid("CSV 存在列数不一致的行，未导入") }
                let date = time.map { row[$0] }.flatMap { $0.isEmpty ? nil : $0 }
                return line(sender: row[sender], message: row[message], time: date)
            }.joined(separator: "\n")
        } else if ext == "json" {
            let object = try JSONSerialization.jsonObject(with: Data(raw.utf8))
            let rows = (object as? [[String: Any]]) ?? (object as? [String: Any])?["messages"] as? [[String: Any]]
            guard let rows = rows else { throw GoutouError.invalid("JSON 需要消息数组，每项含 sender,message，可另含 timestamp") }
            raw = try rows.map { row in
                guard let sender = row["sender"] as? String, let message = row["message"] as? String else { throw GoutouError.invalid("JSON 消息缺少 sender 或 message，未导入") }
                return line(sender: sender, message: message, time: row["timestamp"] as? String)
            }.joined(separator: "\n")
        }
        if ext == "txt" || ext.isEmpty {
            raw = raw.components(separatedBy: .newlines).filter { !$0.trimmed.isEmpty }.map { line in
                ["我：", "我:", "对方：", "对方:", "说话人待确认："].contains(where: { line.hasPrefix($0) }) ? line : "说话人待确认：" + line
            }.joined(separator: "\n")
        }
        guard !raw.trimmed.isEmpty, raw.count <= 12_000 else { throw GoutouError.invalid("每批请导入 1–12000 字；大文件请按日期分批，原文件未修改") }
        return raw
    }
    private static func line(sender: String, message: String, time: String?) -> String {
        let role = ["me": "我", "我": "我", "other": "对方", "对方": "对方"][sender] ?? "说话人待确认"
        return role + "：" + (time.map { "[\($0)] " } ?? "") + (role == "说话人待确认" ? "[\(sender)] " : "") + message
    }
    /// Read a bounded central directory; never extract paths or execute archive contents.
    static func zipTextFiles(_ data: Data) throws -> [(String, Data)] {
        func number(_ at: Int, _ count: Int) throws -> Int {
            guard at >= 0, at + count <= data.count else { throw GoutouError.invalid("ZIP 结构不完整") }
            return (0..<count).reduce(0) { $0 | (Int(data[at + $1]) << ($1 * 8)) }
        }
        guard data.count >= 22 else { throw GoutouError.invalid("ZIP 文件不完整") }
        var end: Int?
        for offset in stride(from: data.count - 22, through: max(0, data.count - 65557), by: -1) {
            if try number(offset, 4) == 0x06054b50 { end = offset; break }
        }
        guard let end = end, try number(end + 4, 2) == 0, try number(end + 6, 2) == 0 else { throw GoutouError.invalid("不支持此 ZIP 或分卷压缩包") }
        let count = try number(end + 10, 2)
        guard count < 2000 else { throw GoutouError.invalid("ZIP 文件数量过多") }
        var cursor = try number(end + 16, 4), result = [(String, Data)]()
        for _ in 0..<count {
            guard try number(cursor, 4) == 0x02014b50 else { throw GoutouError.invalid("ZIP 目录损坏") }
            let flags = try number(cursor + 8, 2), method = try number(cursor + 10, 2)
            let crc = try number(cursor + 16, 4), compressed = try number(cursor + 20, 4), size = try number(cursor + 24, 4)
            let nameCount = try number(cursor + 28, 2), extra = try number(cursor + 30, 2), comment = try number(cursor + 32, 2)
            let local = try number(cursor + 42, 4)
            guard cursor + 46 + nameCount + extra + comment <= end else { throw GoutouError.invalid("ZIP 目录越界") }
            let name = String(data: data.subdata(in: cursor + 46..<cursor + 46 + nameCount), encoding: .utf8) ?? ""
            cursor += 46 + nameCount + extra + comment
            guard ["txt", "csv", "json"].contains((name as NSString).pathExtension.lowercased()), !name.hasPrefix("__MACOSX/") else { continue }
            guard flags & 1 == 0, [0, 8].contains(method), size > 0, size <= maximum, compressed <= 8_000_000 else { throw GoutouError.invalid("正文加密、过大或压缩格式不支持") }
            guard try number(local, 4) == 0x04034b50 else { throw GoutouError.invalid("ZIP 正文损坏") }
            let start = try local + 30 + number(local + 26, 2) + number(local + 28, 2)
            guard start >= 0, start + compressed <= data.count else { throw GoutouError.invalid("ZIP 正文越界") }
            let input = data.subdata(in: start..<start + compressed)
            var output: Data
            if method == 0 { output = input }
            else {
                output = Data(count: size)
                let status: Int32 = input.withUnsafeBytes { source in
                    output.withUnsafeMutableBytes { destination in
                        var stream = z_stream()
                        stream.next_in = UnsafeMutablePointer<Bytef>(mutating: source.bindMemory(to: Bytef.self).baseAddress)
                        stream.avail_in = uInt(input.count)
                        stream.next_out = destination.bindMemory(to: Bytef.self).baseAddress
                        stream.avail_out = uInt(size)
                        guard inflateInit2_(&stream, -MAX_WBITS, ZLIB_VERSION, Int32(MemoryLayout<z_stream>.size)) == Z_OK else { return Z_DATA_ERROR }
                        defer { inflateEnd(&stream) }
                        let status = inflate(&stream, Z_FINISH)
                        return status == Z_STREAM_END && stream.total_out == uLong(size) ? Z_OK : Z_DATA_ERROR
                    }
                }
                guard status == Z_OK else { throw GoutouError.invalid("ZIP 解压失败，未导入") }
            }
            let actual = output.withUnsafeBytes { crc32(0, $0.bindMemory(to: Bytef.self).baseAddress, uInt(output.count)) }
            guard output.count == size, actual == uLong(crc) else { throw GoutouError.invalid("ZIP 正文校验失败，未导入") }
            result.append((name, output))
            guard result.count <= 1 else { throw GoutouError.invalid("ZIP 有多份正文，请解压后分别选择导入") }
        }
        return result
    }
}

struct SharedChatImport: Codable, Identifiable {
    var id = UUID()
    var text: String
    var source: String
    var receivedAt = Date()
}

struct SharedImportInbox {
    let container: URL
    private var folder: URL { container.appendingPathComponent("SharedImports", isDirectory: true) }
    func pending() throws -> [SharedChatImport] {
        guard FileManager.default.fileExists(atPath: folder.path) else { return [] }
        let key = try MemoryEncryptionKey.load()
        return try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.fileSizeKey]).filter { $0.pathExtension == "bin" }.map { url in
            guard let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 100_000 else { throw GoutouError.invalid("共享内容过大") }
            return try JSONDecoder().decode(SharedChatImport.self, from: AES.GCM.open(AES.GCM.SealedBox(combined: Data(contentsOf: url)), using: key))
        }.sorted { $0.receivedAt < $1.receivedAt }
    }
    func save(_ item: SharedChatImport) throws {
        guard item.text.count <= 12_000 else { throw GoutouError.invalid("共享文本每批最多 12000 字") }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        guard try pending().count < 10 else { throw GoutouError.invalid("请先在主 App 接收已有的共享内容") }
        let data = try AES.GCM.seal(JSONEncoder().encode(item), using: MemoryEncryptionKey.load()).combined!
        let url = folder.appendingPathComponent(item.id.uuidString + ".bin")
        #if os(iOS)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        #else
        try data.write(to: url, options: .atomic)
        #endif
        var excluded = url; var values = URLResourceValues(); values.isExcludedFromBackup = true; try excluded.setResourceValues(values)
    }
    func remove(_ id: UUID) throws { try FileManager.default.removeItem(at: folder.appendingPathComponent(id.uuidString + ".bin")) }
}
