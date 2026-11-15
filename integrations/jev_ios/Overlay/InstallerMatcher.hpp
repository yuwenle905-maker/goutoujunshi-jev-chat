#pragma once
#include <stdint.h>
#include <stddef.h>

// Known TrollSpeed ARM64 caller shape, not a general code scanner. The caller
// supplies readable words and a validating callback; no target is invoked here.
static inline bool AleInstallerEntry(uint32_t word) {
    return (word & 0xff00001f) == 0xb4000000; // cbz x0, ...
}
static inline uintptr_t AleFindInstaller(const uint32_t *words, size_t count, uintptr_t base,
                                       bool (*validate)(uintptr_t, void *), void *context) {
    if (!words || !validate || count < 3) return 0;
    uintptr_t match = 0;
    for (size_t i = 0; i + 2 < count; ++i) {
        if (words[i] != 0xaa0003e2 || (words[i + 1] & 0xff00001f) != 0xaa000000) continue;
        uint32_t branch = words[i + 2];
        if ((branch & 0xfc000000) != 0x94000000) continue;
        int64_t relative = branch & 0x03ffffff;
        if (relative & 0x02000000) relative -= 0x04000000;
        uintptr_t target = base + (i + 2) * 4 + relative * 4;
        if (!target || !validate(target, context)) continue;
        if (match && match != target) return 0;
        match = target;
    }
    return match;
}
