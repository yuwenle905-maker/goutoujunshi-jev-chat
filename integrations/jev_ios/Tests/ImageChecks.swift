import AppKit
import ImageIO
import UniformTypeIdentifiers

/// Exercises the production decoder and Vision OCR with generated, non-private chat pixels.
@main
struct ImageChecks {
    static var count = 0
    static func check(_ name: String, _ condition: @autoclosure () -> Bool) throws {
        guard condition() else { throw GoutouError.invalid(name) }
        count += 1
    }
    static func rejects(_ name: String, _ body: () throws -> Void) throws {
        do { try body() } catch { count += 1; return }
        throw GoutouError.invalid(name)
    }
    @MainActor static func fixture() throws -> Data {
        let canvas = NSImage(size: NSSize(width: 900, height: 700))
        canvas.lockFocus()
        NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 900, height: 700).fill()
        func line(_ text: String, x: CGFloat, y: CGFloat) {
            (text as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: [
                .font: NSFont.systemFont(ofSize: 32), .foregroundColor: NSColor.black
            ])
        }
        line("周末安排", x: 380, y: 610)
        line("这周有点忙", x: 55, y: 485)
        line("嗯，你先忙", x: 630, y: 350)
        line("下周再看看吧", x: 55, y: 215)
        canvas.unlockFocus()
        guard let tiff = canvas.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else {
            throw GoutouError.invalid("Fixture rendering failed")
        }
        return png
    }
    @MainActor static func darkFixture(statusOnly: Bool = false) throws -> Data {
        let canvas = NSImage(size: NSSize(width: 1170, height: 2532))
        canvas.lockFocus()
        NSColor(calibratedWhite: 0.06, alpha: 1).setFill()
        NSRect(x: 0, y: 0, width: 1170, height: 2532).fill()
        func line(_ text: String, x: CGFloat, y: CGFloat, color: NSColor = .white) {
            (text as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: [.font: NSFont.systemFont(ofSize: 48), .foregroundColor: color])
        }
        line("02:24", x: 65, y: 2420); line("64", x: 1040, y: 2420)
        if !statusOnly {
            line("测试聊天", x: 450, y: 2260)
            NSColor(calibratedWhite: 0.18, alpha: 1).setFill()
            NSRect(x: 150, y: 1780, width: 680, height: 120).fill()
            line("今天先处理工作", x: 180, y: 1810, color: NSColor(calibratedWhite: 0.7, alpha: 1))
            line("知道了，你先忙", x: 680, y: 1550)
            line("12:08", x: 495, y: 1370, color: .gray)
            line("64", x: 975, y: 1150) // A genuine numeric message, outside status area.
        }
        canvas.unlockFocus()
        guard let tiff = canvas.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else { throw GoutouError.invalid("Dark fixture failed") }
        return png
    }
    @MainActor static func main() async {
        do {
            let png = try fixture()
            if let path = CommandLine.arguments.dropFirst().first { try png.write(to: URL(fileURLWithPath: path)) }
            let source = try LocalOCR.image(png)
            try check("Fixture dimensions", source.width >= 900 && source.height >= 700)
            let jpeg = try LocalOCR.boundedJPEG(png, maxPixelSize: 600)
            let bounded = try LocalOCR.image(jpeg)
            try check("Keyboard image is downsampled", max(bounded.width, bounded.height) == 600)
            try check("JPEG stays within request size", jpeg.count <= 4_000_000)
            let cropped = try LocalOCR.boundedJPEG(png, maxPixelSize: 600, excludedBottomFraction: 0.35)
            let croppedImage = try LocalOCR.image(cropped)
            try check("Keyboard bottom region excluded", croppedImage.width == bounded.width && croppedImage.height == Int(Double(bounded.height) * 0.65))
            try rejects("Reject non-finite crop") { _ = try LocalOCR.boundedJPEG(png, excludedBottomFraction: .nan) }
            try rejects("Reject oversized crop") { _ = try LocalOCR.boundedJPEG(png, excludedBottomFraction: 0.8) }
            let encodedSource = CGImageSourceCreateWithData(jpeg as CFData, nil)!
            try check("Normalized JPEG format", CGImageSourceGetType(encodedSource) as String? == UTType.jpeg.identifier)
            try rejects("Reject invalid image bytes") { _ = try LocalOCR.image(Data("not an image".utf8)) }
            try rejects("Reject empty image") { _ = try LocalOCR.image(Data()) }
            try rejects("Reject oversized input before decoding") { _ = try LocalOCR.image(Data(count: 20_000_001)) }

            let rotated = NSMutableData()
            let destination = CGImageDestinationCreateWithData(rotated, UTType.tiff.identifier as CFString, 1, nil)!
            CGImageDestinationAddImage(destination, source, [kCGImagePropertyOrientation: 6,
                kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 1.0]] as CFDictionary)
            guard CGImageDestinationFinalize(destination) else { throw GoutouError.invalid("Rotation fixture failed") }
            let normalized = try LocalOCR.boundedJPEG(rotated as Data, maxPixelSize: 600)
            let normalizedSource = CGImageSourceCreateWithData(normalized as CFData, nil)!
            let rotatedImage = try LocalOCR.image(normalized)
            try check("Orientation applied to pixels", rotatedImage.height > rotatedImage.width)
            let properties = CGImageSourceCopyPropertiesAtIndex(normalizedSource, 0, nil) as? [String: Any]
            try check("Source location metadata not copied", properties?[kCGImagePropertyGPSDictionary as String] == nil)

            let transcript = try await LocalOCR.recognize(png, maxPixelSize: 1600)
            let compact = transcript.replacingOccurrences(of: " ", with: "")
            try check("Chinese left bubble assigned for review", compact.contains("对方：这周有点忙"))
            try check("Chinese right bubble assigned for review", compact.contains("我：嗯") && compact.contains("你先忙"))
            try check("Reading order preserved", compact.range(of: "这周有点忙")!.lowerBound < compact.range(of: "下周再看看吧")!.lowerBound)
            try check("Centered text remains unresolved", compact.contains("说话人待确认：周末安排"))
            let croppedText = try await LocalOCR.recognize(cropped).replacingOccurrences(of: " ", with: "")
            try check("Crop preserves top chat and removes bottom content", croppedText.contains("这周有点忙") && !croppedText.contains("下周再看看吧"))
            try rejects("Unresolved OCR cannot go directly to analysis") { try Transcript(text: transcript, confirmed: true).validate() }
            var config = AppConfig()
            let localRequest = KeyboardCaptureRequest(relationship: Relationship(id: "fixture"), config: config, excludedBottomFraction: 0.4)
            let localResult = try await CaptureOCR.prepare(jpeg, request: localRequest)
            try check("Local capture uses Vision and returns text", localResult.transcript.contains("这周") && localResult.screenshot == nil)
            let dark = try darkFixture()
            let darkText = try await LocalOCR.recognize(dark)
            try check("Dark Chinese chat recognized", darkText.replacingOccurrences(of: " ", with: "").contains("今天先处理工作"))
            try check("Status time and centered timestamp excluded", !darkText.contains("02:24") && !darkText.contains("12:08"))
            try check("Numeric chat message retained", darkText.contains("64"))
            let croppedDark = try LocalOCR.boundedJPEG(dark, maxPixelSize: 2000, excludedBottomFraction: 0.35)
            let capturedDark = try await CaptureOCR.prepare(croppedDark, request: localRequest)
            try check("Cropped capture keeps Chinese but rejects status", capturedDark.transcript.contains("今天") && !capturedDark.transcript.contains("02:24"))
            do {
                _ = try await LocalOCR.recognize(darkFixture(statusOnly: true))
                throw GoutouError.invalid("Status-only image accepted as chat")
            } catch GoutouError.invalid(let message) where message != "Status-only image accepted as chat" { count += 1 }
            for provider in [OCRProvider.deepseek, .openrouter] {
                config.ocr = provider; config.visionModel = "fixture-vision"
                let request = KeyboardCaptureRequest(relationship: localRequest.relationship, config: config, excludedBottomFraction: 0.4)
                let result = try await CaptureOCR.prepare(jpeg, request: request)
                try check("\(provider) capture returns image awaiting confirmation", result.screenshot == jpeg)
                try check("\(provider) capture does not perform local OCR", result.transcript.isEmpty && result.error == nil)
                do {
                    _ = try await CaptureOCR.prepare(Data("not an image".utf8), request: request)
                    throw GoutouError.invalid("Invalid cloud capture accepted")
                } catch GoutouError.invalid(let message) where message != "Invalid cloud capture accepted" { count += 1 }
            }
            let canceledCapture = Task { try await CaptureOCR.prepare(jpeg, request: localRequest) }
            canceledCapture.cancel()
            do { _ = try await canceledCapture.value; throw GoutouError.invalid("Canceled capture returned content") }
            catch is CancellationError { count += 1 }
            let canceled = Task { try await LocalOCR.recognize(png) }
            canceled.cancel()
            do { _ = try await canceled.value; throw GoutouError.invalid("Canceled OCR returned text") }
            catch is CancellationError { count += 1 }
            print("PASS: \(count) screenshot/OCR checks; generated chat image, no network requests")
        } catch { fputs("FAIL: \(error)\n", stderr); exit(1) }
    }
}
