import SwiftUI

struct BrandPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.callout.weight(.semibold))
            .frame(minHeight: 24)
            .padding(.horizontal, 16).padding(.vertical, 10)
            .foregroundStyle(Palette.onPrimary)
            .background(Palette.primary.opacity(isEnabled ? 1 : 0.35), in: Capsule())
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

struct ShibaBadge: View {
    var size: CGFloat = 52
    var body: some View {
        Image("AleMark").resizable().scaledToFit()
            .frame(width: size, height: size)
            .clipShape(RoundedRectangle(cornerRadius: size * 0.24))
            .accessibilityHidden(true)
    }
}
