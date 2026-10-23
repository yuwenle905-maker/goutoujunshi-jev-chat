import Foundation
import Vision
import ImageIO
import UniformTypeIdentifiers
import CoreImage

/// Capture processes never upload images. The configured cloud providers receive
/// a preview in the keyboard, then its explicit upload button invokes ModelAPI.
enum CaptureOCR {
    static func prepare(_ jpeg: Data, request: KeyboardCaptureRequest) async throws -> KeyboardCaptureResult {
        try Task.checkCancellation()
        if request.config.ocr == .local {
            let text = try await LocalOCR.recognize(jpeg, maxPixelSize: 2200, screenCapture: true)
            return KeyboardCaptureResult(request: request, transcript: text)
        }
        guard jpeg.count <= 4_000_000 else { throw GoutouError.invalid("截图过大，请重新截屏") }
        _ = try LocalOCR.image(jpeg, maxPixelSize: 480) // Decode only; no Vision recognition.
        return KeyboardCaptureResult(request: request, transcript: "", screenshot: jpeg)
    }
}

/// Shared by the app and keyboard. Decode a bounded thumbnail rather than a full-resolution photo.
enum LocalOCR {
    static func image(_ data: Data, maxPixelSize: Int = 2000) throws -> CGImage {
        guard !data.isEmpty, data.count <= 20_000_000,
              let source = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceThumbnailMaxPixelSize: maxPixelSize,
                kCGImageSourceShouldCacheImmediately: true
              ] as CFDictionary) else {
            throw GoutouError.invalid("图片无法读取，请选择 20 MB 以内的聊天截图")
        }
        return image
    }
    static func boundedJPEG(_ data: Data, maxPixelSize: Int = 2000, excludedBottomFraction: Double = 0) throws -> Data {
        guard excludedBottomFraction.isFinite, (0...0.7).contains(excludedBottomFraction) else {
            throw GoutouError.invalid("截图裁剪范围无效，请重新准备识图")
        }
        let full = try image(data, maxPixelSize: maxPixelSize)
        guard let image = full.cropping(to: CGRect(x: 0, y: 0, width: full.width,
              height: max(1, Int(Double(full.height) * (1 - excludedBottomFraction))))) else {
            throw GoutouError.invalid("截图裁剪失败，请重新准备识图")
        }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw GoutouError.invalid("截图转换失败，请换一张图片")
        }
        // Re-encode visible pixels only; no source EXIF, location, or other metadata is copied.
        CGImageDestinationAddImage(destination, image, [kCGImageDestinationLossyCompressionQuality: 0.85] as CFDictionary)
        guard CGImageDestinationFinalize(destination), output.length <= 4_000_000 else {
            throw GoutouError.invalid("截图过大，请裁小聊天范围")
        }
        return output as Data
    }
    static func recognize(_ data: Data, maxPixelSize: Int = 2000, screenCapture: Bool = false) async throws -> String {
        let job = Task.detached(priority: .userInitiated) {
            try Task.checkCancellation()
            let cgImage = try Self.image(data, maxPixelSize: maxPixelSize)
            struct Line {
                var text: String
                var box: CGRect
                var confidence: Float
                var han: Int { text.unicodeScalars.filter { (0x3400...0x9fff).contains($0.value) }.count }
            }
            func scan(_ image: CGImage, top: Double = 0, fraction: Double = 1) throws -> [Line] {
                try Task.checkCancellation()
                let request = VNRecognizeTextRequest()
                request.recognitionLevel = .accurate
                request.recognitionLanguages = ["zh-Hans", "en-US"]
                request.usesLanguageCorrection = true
                request.minimumTextHeight = 0.008
                try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
                return (request.results ?? []).compactMap { row in
                    guard let candidate = row.topCandidates(1).first, !candidate.string.trimmed.isEmpty else { return nil }
                    let box = row.boundingBox
                    return Line(text: candidate.string.trimmed,
                        box: CGRect(x: box.minX, y: (1 - top - fraction) + box.minY * fraction,
                                    width: box.width, height: box.height * fraction), confidence: candidate.confidence)
                }
            }
            var rows = try scan(cgImage)
            let context = CIContext(options: [.cacheIntermediates: false])
            if rows.reduce(0, { $0 + $1.han }) < 4 {
                let inverted = CIImage(cgImage: cgImage).applyingFilter("CIColorInvert")
                if let light = context.createCGImage(inverted, from: inverted.extent) {
                    let retry = try scan(light)
                    if retry.reduce(0, { $0 + $1.han }) > rows.reduce(0, { $0 + $1.han }) || rows.isEmpty { rows = retry }
                }
            }
            // A successful upper half says nothing about missed green bubbles below it.
            // Always rescan overlapping strips; map their boxes back into full-image coordinates.
            for (top, fraction) in [(0.06, 0.40), (0.36, 0.40), (0.64, 0.36)] {
                try Task.checkCancellation()
                let rect = CGRect(x: 0, y: Double(cgImage.height) * top, width: Double(cgImage.width), height: Double(cgImage.height) * fraction).integral
                    .intersection(CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height))
                guard let tile = cgImage.cropping(to: rect) else { continue }
                let actualTop = rect.minY / Double(cgImage.height), actualFraction = rect.height / Double(cgImage.height)
                let additions: [Line] = try autoreleasepool {
                    let gray = CIImage(cgImage: tile).applyingFilter("CIColorControls", parameters: [
                        kCIInputSaturationKey: 0, kCIInputContrastKey: 1.35
                    ])
                    let ready = context.createCGImage(gray, from: gray.extent) ?? tile
                    return try scan(ready, top: actualTop, fraction: actualFraction)
                }
                for line in additions {
                    if let index = rows.firstIndex(where: { previous in
                        let overlap = previous.box.intersection(line.box)
                        return !overlap.isNull && overlap.height >= min(previous.box.height, line.box.height) * 0.6 &&
                            overlap.width >= min(previous.box.width, line.box.width) * 0.55
                    }) {
                        let previous = rows[index]
                        if (line.han > previous.han && line.confidence >= previous.confidence - 0.12) ||
                            (line.confidence > previous.confidence + 0.15 && line.han >= previous.han) { rows[index] = line }
                    } else { rows.append(line) }
                }
            }
            try Task.checkCancellation()
            let portrait = Double(cgImage.height) / Double(cgImage.width) > 1.5
            let observations = rows.filter { row in
                if (portrait || screenCapture) && (row.box.midY > 0.88 || row.box.midY < 0.10) { return false }
                if row.box.midX > 0.30 && row.box.midX < 0.70 &&
                    row.text.range(of: "^(?:[0-9]{1,2}月[0-9]{1,2}日\\s*)?[0-9]{1,2}\\s*[:：]\\s*[0-9]{2}$", options: .regularExpression) != nil { return false }
                return true
            }.sorted { left, right in
                if left.box.midY == right.box.midY { return left.box.minX < right.box.minX }
                return left.box.midY > right.box.midY
            }
            let lines = observations.compactMap { observation -> String? in
                let text = observation.text
                guard !text.trimmed.isEmpty else { return nil }
                let x = observation.box.midX
                let speaker = x > 0.58 ? "我" : (x < 0.42 ? "对方" : "说话人待确认")
                return speaker + "：" + text
            }
            let text = lines.joined(separator: "\n")
            guard !text.isEmpty, text.count <= 12_000 else { throw GoutouError.invalid("没有识别到有效聊天文字。请先收起键盘再截屏，或从相册选择清晰的完整聊天截图；时间和电量不作为聊天。") }
            return text
        }
        return try await withTaskCancellationHandler(operation: { try await job.value }, onCancel: { job.cancel() })
    }
}
