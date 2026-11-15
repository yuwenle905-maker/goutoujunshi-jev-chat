#include "../Overlay/InstallerMatcher.hpp"
#include <assert.h>
#include <stdio.h>

static unsigned checks;
static void check(bool condition) { ++checks; assert(condition); }
static bool allow(uintptr_t target, void *data) { return target == *(uintptr_t *)data; }
static bool all(uintptr_t, void *) { return true; }
static uint32_t branch(uintptr_t from, uintptr_t to) {
    int64_t offset = ((int64_t)to - (int64_t)from) / 4;
    return 0x94000000 | ((uint32_t)offset & 0x03ffffff);
}
int main() {
    uintptr_t base = 0x1000, wanted = 0x1800;
    uint32_t code[12] = {0xaa0003e2, 0xaa0103e0, branch(base + 8, wanted)};
    check(AleFindInstaller(code, 12, base, allow, &wanted) == wanted);
    wanted = 0x800; code[2] = branch(base + 8, wanted);
    check(AleFindInstaller(code, 12, base, allow, &wanted) == wanted); // signed backwards BL
    check(AleFindInstaller(code, 2, base, all, nullptr) == 0); // bounded lookahead
    check(AleFindInstaller(nullptr, 12, base, all, nullptr) == 0);
    check(AleFindInstaller(code, 12, base, nullptr, nullptr) == 0);
    wanted = 0x2000;
    check(AleFindInstaller(code, 12, base, allow, &wanted) == 0); // unreadable/wrong-image targets rejected by validator
    code[0] = 0;
    check(AleFindInstaller(code, 12, base, all, nullptr) == 0);
    code[0] = 0xaa0003e2; code[1] = 0xaa0103e1;
    check(AleFindInstaller(code, 12, base, all, nullptr) == 0); // destination must be x0
    code[1] = 0xaa0103e0; code[2] = 0x14000000;
    check(AleFindInstaller(code, 12, base, all, nullptr) == 0); // B is not BL
    code[2] = branch(base + 8, 0x1800);
    code[4] = code[0]; code[5] = code[1]; code[6] = branch(base + 24, 0x1900);
    check(AleFindInstaller(code, 12, base, all, nullptr) == 0); // ambiguous cannot invoke
    code[6] = branch(base + 24, 0x1800);
    check(AleFindInstaller(code, 12, base, all, nullptr) == 0x1800); // repeated same target is unique
    check(AleInstallerEntry(0xb4000040));
    check(!AleInstallerEntry(0xb4000041)); // cbz x1 is not accepted
    check(!AleInstallerEntry(0xd503201f));
    printf("PASS: %u bounded ARM64 installer resolution checks; no UIKit invocation\n", checks);
}
