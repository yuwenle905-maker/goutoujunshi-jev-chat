// Adapted from TrollSpeed, Copyright (c) 2023 Lessica, MIT (see LICENSE).
// UIKit's own sources MUST exist even though AX touches use an independent source.
#import <notify.h>
#import <objc/runtime.h>
#import "UIEventFetcher.h"
#import "UIEventDispatcher.h"
#import "HUDMainApplication.h"
#import "InstallerMatcher.hpp"
#import <mach/mach.h>
#import <dlfcn.h>
#import <string.h>

static bool ReadWords(uintptr_t address, uint32_t *words, size_t bytes) {
    vm_size_t read = 0;
    return vm_read_overwrite(mach_task_self(), (vm_address_t)address, bytes,
        (vm_address_t)words, &read) == KERN_SUCCESS && read == bytes;
}
static bool PointerField(id object, const char *name, size_t *offset, void **value) {
    Ivar ivar = class_getInstanceVariable(object_getClass(object), name);
    if (!ivar || !ivar_getTypeEncoding(ivar) || ivar_getTypeEncoding(ivar)[0] != '^') return false;
    ptrdiff_t position = ivar_getOffset(ivar);
    if (position < 0 || (size_t)position + sizeof(void *) > class_getInstanceSize(object_getClass(object))) return false;
    if (offset) *offset = (size_t)position;
    if (value) memcpy(value, (const char *)(__bridge void *)object + position, sizeof(void *));
    return true;
}
static bool NativeSourcesReady(id dispatcher) {
    void *source = nullptr, *loop = nullptr;
    return PointerField(dispatcher, "_collectHIDEventsRunLoopSource", nullptr, &source) &&
        PointerField(dispatcher, "_runLoop", nullptr, &loop) && source && loop == CFRunLoopGetMain() &&
        CFRunLoopContainsSource(CFRunLoopGetMain(), (CFRunLoopSourceRef)source, kCFRunLoopCommonModes);
}
struct InstallerContext { void *image; size_t loopOffset; };
static bool ValidateInstaller(uintptr_t address, unsigned args, void *raw) {
    auto context = (InstallerContext *)raw;
    Dl_info image = {}; uint32_t body[24];
    return dladdr((void *)address, &image) && image.dli_fbase == context->image &&
        ReadWords(address, body, sizeof(body)) &&
        AleInstallerStoresRunLoop(body, 24, args, context->loopOffset);
}
static bool InstallNativeSources(id dispatcher, UIApplication *app) {
    if (NativeSourcesReady(dispatcher)) return true;
    if ([dispatcher respondsToSelector:@selector(_installEventRunLoopSources:)]) {
        [dispatcher _installEventRunLoopSources:CFRunLoopGetMain()];
    } else {
        size_t loopOffset = 0;
        if (!PointerField(dispatcher, "_runLoop", &loopOffset, nullptr)) return false;
        IMP run = class_getMethodImplementation(app.class, NSSelectorFromString(@"_run"));
        Dl_info image = {}; uint32_t words[1024];
        if (!run || !dladdr((void *)run, &image) || !ReadWords((uintptr_t)run, words, sizeof(words))) return false;
        InstallerContext context = {image.dli_fbase, loopOffset};
        AleInstaller match = AleFindInstaller(words, 1024, (uintptr_t)run, ValidateInstaller, &context);
        if (!match.address) return false;
        if (match.arguments == 2) {
            ((void(*)(id, CFRunLoopRef))match.address)(dispatcher, CFRunLoopGetMain());
        } else {
            ((void(*)(id, SEL, CFRunLoopRef))match.address)(dispatcher,
                @selector(_installEventRunLoopSources:), CFRunLoopGetMain());
        }
    }
    // Never attach a sink, or enter plugin startup, on an uninitialized source.
    return NativeSourcesReady(dispatcher);
}

@interface HUDMainApplication ()
@property (nonatomic, readwrite) BOOL aleEventsReady;
@property (nonatomic, copy, readwrite) NSString *aleEventStage;
@end

@implementation HUDMainApplication
- (instancetype)init {
    if ((self = [super init])) {
        self.aleEventStage = @"等待UIApplication单例注册";
        int token;
        notify_register_dispatch(NOTIFY_DISMISSAL_HUD, &token, dispatch_get_main_queue(), ^(int t) {
            notify_cancel(t); exit(0);
        });
    }
    return self;
}
- (BOOL)prepareAleEvents {
    if (self.aleEventsReady) return YES;
    @try {
        self.aleEventStage = @"获取事件分发器";
        UIEventDispatcher *dispatcher = [self valueForKey:@"eventDispatcher"];
        if (!dispatcher) { self.aleEventStage = @"事件分发器尚未创建"; return NO; }
        self.aleEventStage = @"安装并核验UIKit原生事件源";
        if (!InstallNativeSources(dispatcher, self)) {
            self.aleEventStage = @"UIKit原生事件源未建立，已停止绑定，避免启动崩溃";
            return NO;
        }
        self.aleEventStage = @"创建UIEventFetcher";
        UIEventFetcher *fetcher = [[NSClassFromString(@"UIEventFetcher") alloc] init];
        if (!fetcher) return NO;
        self.aleEventStage = @"绑定事件分发器的Fetcher";
        [dispatcher setValue:fetcher forKey:@"eventFetcher"];
        self.aleEventStage = @"绑定Fetcher接收端";
        if ([fetcher respondsToSelector:@selector(setEventFetcherSink:)]) [fetcher setEventFetcherSink:dispatcher];
        else [fetcher setValue:dispatcher forKey:@"eventFetcherSink"];
        self.aleEventStage = @"绑定UIApplication的Fetcher";
        [self setValue:fetcher forKey:@"eventFetcher"];
        self.aleEventsReady = YES;
        self.aleEventStage = @"Fetcher已绑定，等待独立触摸事件源自检";
    } @catch (NSException *e) {
        self.aleEventStage = [self.aleEventStage stringByAppendingString:@"：接口调用异常"];
        self.aleEventsReady = NO;
    }
    return self.aleEventsReady;
}
@end
