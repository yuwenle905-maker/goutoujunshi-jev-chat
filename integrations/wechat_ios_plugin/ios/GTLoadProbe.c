// Build as a separate dylib. Inject ONLY this probe to isolate loading from ObjC/UI hooks.
#include "GTBoot.h"
__attribute__((constructor)) static void GoutouLoadProbeEntry(void) {
    GoutouWechatAI_BootMark("load_probe_0_1_1_entered");
}
