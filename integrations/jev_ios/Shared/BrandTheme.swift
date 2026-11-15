#if canImport(UIKit)
import UIKit

/// Shared by the app and its keyboard so their light and dark appearances stay consistent.
enum BrandTheme {
    private static func adaptive(_ light: UInt32, _ dark: UInt32) -> UIColor {
        UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((hex >> 16) & 255) / 255,
                           green: CGFloat((hex >> 8) & 255) / 255,
                           blue: CGFloat(hex & 255) / 255, alpha: 1)
        }
    }

    static let background = adaptive(0xF2F6F5, 0x101A18)
    static let surface = adaptive(0xFFFFFF, 0x1B2925)
    static let highlight = adaptive(0xE0EEE8, 0x2B4137)
    static let accent = adaptive(0x19674F, 0x83DAB8)
    static let primary = adaptive(0x19674F, 0x83DAB8)
    static let onPrimary = adaptive(0xFFFFFF, 0x10251C)
    static let text = adaptive(0x192D25, 0xEFF7F3)
    static let secondaryText = adaptive(0x596B63, 0xAFBFB6)
    static let separator = adaptive(0xD6E2DC, 0x40584C)
    static let chartRise = adaptive(0x19674F, 0x83DAB8)
    static let chartFall = adaptive(0x6B7771, 0xA7B6AE)
    static let chartEvent = adaptive(0x99651B, 0xE6BA6B)
}
#endif
