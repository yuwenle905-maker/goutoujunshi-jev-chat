#include "../Overlay/InstallerMatcher.hpp"
#include <assert.h>
#include <stdio.h>
static unsigned checked = 0;
static bool validate(uintptr_t target, unsigned args, void *raw) {
    auto expected = (AleInstaller *)raw;
    return target == expected->address && args == expected->arguments;
}
#define CHECK(x) do { assert(x); ++checked; } while (0)
int main() {
    // Equivalent ARM64 instruction shapes, not bytes from a user's device.
    const uint32_t two[] = {0xb4000100, 0xf9001401}; // cbz x0; str x1,[x0,#40]
    const uint32_t three[] = {0xb4000100, 0xf9001402};
    CHECK(AleInstallerStoresRunLoop(two, 2, 2, 40));
    CHECK(AleInstallerStoresRunLoop(three, 2, 3, 40));
    CHECK(!AleInstallerStoresRunLoop(two, 2, 3, 40));
    CHECK(!AleInstallerStoresRunLoop(three, 2, 2, 40));
    CHECK(!AleInstallerStoresRunLoop(two, 2, 2, 48));
    CHECK(!AleInstallerStoresRunLoop(nullptr, 0, 2, 40));
    const uint32_t moved[] = {0xd503233f, 0xa9bf7bfd, 0xaa0003f3, 0xaa0103f4, 0xf9001674};
    CHECK(AleInstallerStoresRunLoop(moved, 5, 2, 40)); // PAC, stack, register moves
    const uint32_t clobbered[] = {0x94000001, 0xf9001401};
    CHECK(!AleInstallerStoresRunLoop(clobbered, 2, 2, 40)); // call before store
    const uint32_t wrongbase[] = {0xf9001421}; // str x1,[x1,#40]
    CHECK(!AleInstallerStoresRunLoop(wrongbase, 1, 2, 40));
    uint32_t caller[] = {0xaa0003e1, 0xaa1303e0, 0x94000002};
    AleInstaller expected = {0x1010, 2};
    auto match = AleFindInstaller(caller, 3, 0x1000, validate, &expected);
    CHECK(match.address == 0x1010 && match.arguments == 2);
    expected.arguments = 3;
    CHECK(!AleFindInstaller(caller, 3, 0x1000, validate, &expected).address);
    caller[0] = 0xaa0003e2;
    CHECK(AleFindInstaller(caller, 3, 0x1000, validate, &expected).arguments == 3);
    caller[2] = 0x97fffffc; expected.address = 0xff8;
    CHECK(AleFindInstaller(caller, 3, 0x1000, validate, &expected).address == 0xff8);
    caller[2] = 0x14000002;
    CHECK(!AleFindInstaller(caller, 3, 0x1000, validate, &expected).address);
    CHECK(!AleFindInstaller(caller, 2, 0x1000, validate, &expected).address);
    uint32_t ambiguous[] = {0xaa0003e1, 0xaa1303e0, 0x94000002, 0xaa0003e1, 0xaa1303e0, 0x94000002};
    auto accept = [](uintptr_t, unsigned, void *) { return true; };
    CHECK(!AleFindInstaller(ambiguous, 6, 0x1000, accept, nullptr).address);
    printf("PASS: %u installer checks (2/3 argument ABI, stores, clobber, branches, ambiguity)\n", checked);
}
