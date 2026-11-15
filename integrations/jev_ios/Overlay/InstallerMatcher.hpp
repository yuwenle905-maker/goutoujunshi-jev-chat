#pragma once
#include <stdint.h>
#include <stddef.h>

// Hidden UIKit implementations may omit _cmd. The caller's register assignment
// AND the callee's store of the runloop must agree before invoking either ABI.
struct AleInstaller {
    uintptr_t address; unsigned arguments;
    AleInstaller(uintptr_t value = 0, unsigned count = 0) : address(value), arguments(count) {}
};
static inline bool AleInstallerStoresRunLoop(const uint32_t *words, size_t count,
                                            unsigned arguments, size_t offset) {
    if (!words || (arguments != 2 && arguments != 3)) return false;
    unsigned tags[32] = {}; tags[0] = 1; tags[arguments - 1] = 2;
    for (size_t i = 0; i < count && i < 24; ++i) {
        uint32_t w = words[i];
        if ((w & 0xffe0ffe0) == 0xaa0003e0) { // mov Xd, Xm
            tags[w & 31] = tags[(w >> 16) & 31]; continue;
        }
        if ((w & 0xffc00000) == 0xf9000000) { // str Xt, [Xn, #imm]
            if (tags[w & 31] == 2 && tags[(w >> 5) & 31] == 1 &&
                ((w >> 10) & 4095) * 8 == offset) return true;
            continue;
        }
        // Only known non-mutating guards/prologue instructions are accepted.
        if ((w & 0x7e000000) == 0x34000000 || // cbz/cbnz
            (w & 0xffc003e0) == 0xa98003e0 || // stp ..., [sp, #-imm]!
            (w & 0xffc003e0) == 0xa90003e0 || // stp ..., [sp, #imm]
            (w & 0xfffffc1f) == 0xd503201f || // hints / BTI / PAC
            (w & 0xffc003ff) == 0x910003fd || // add fp, sp, #imm
            (w & 0xffc003ff) == 0xd10003ff) continue; // sub sp, sp, #imm
        return false;
    }
    return false;
}
static inline AleInstaller AleFindInstaller(const uint32_t *words, size_t count, uintptr_t base,
                            bool (*validate)(uintptr_t, unsigned, void *), void *context) {
    AleInstaller found;
    if (!words || !validate || count < 3) return found;
    for (size_t i = 0; i + 2 < count; ++i) {
        unsigned args = words[i] == 0xaa0003e1 ? 2 : words[i] == 0xaa0003e2 ? 3 : 0;
        if (!args || (words[i + 1] & 0xffe0ffff) != 0xaa0003e0) continue;
        uint32_t branch = words[i + 2];
        if ((branch & 0xfc000000) != 0x94000000) continue;
        int64_t relative = branch & 0x03ffffff;
        if (relative & 0x02000000) relative -= 0x04000000;
        uintptr_t target = base + (i + 2) * 4 + relative * 4;
        if (!target || !validate(target, args, context)) continue;
        if (found.address && (found.address != target || found.arguments != args)) return {};
        found = {target, args};
    }
    return found;
}
