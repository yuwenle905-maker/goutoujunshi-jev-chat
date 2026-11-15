// Adapted from TrollSpeed, Copyright (c) 2023 Lessica, MIT (see LICENSE).
// Ale: initialize after singleton registration; restore upstream ARM64 installer
// resolution with bounded self reads, image validation and ambiguity rejection.
#import <notify.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import <mach/mach.h>
#import "pac_helper.h"
#import "UIEventFetcher.h"
#import "UIEventDispatcher.h"
#import "HUDMainApplication.h"
#include "../InstallerMatcher.hpp"

typedef void (*Installer)(id, SEL, CFRunLoopRef);

static Installer ResolveInstaller(void) {
#if defined(__arm64__)
    IMP run = class_getMethodImplementation(UIApplication.class, NSSelectorFromString(@"_run"));
    if (!run) return NULL;
    uintptr_t address = (uintptr_t)make_sym_readable((void *)run);
    uint32_t words[0x142] = {};
    vm_size_t copied = 0;
    if (vm_read_overwrite(mach_task_self(), address, sizeof(words), (vm_address_t)words, &copied) != KERN_SUCCESS || copied != sizeof(words)) return NULL;
    Dl_info origin = {};
    if (!dladdr((void *)address, &origin) || !origin.dli_fbase) return NULL;
    uintptr_t target = AleFindInstaller(words, 0x142, address, [](uintptr_t target, void *context) -> bool {
        Dl_info *origin = (Dl_info *)context;
        Dl_info info = {};
        if (!dladdr((void *)target, &info) || info.dli_fbase != origin->dli_fbase) return false;
        uint32_t first = 0; vm_size_t copied = 0;
        if (vm_read_overwrite(mach_task_self(), target, sizeof(first), (vm_address_t)&first, &copied) != KERN_SUCCESS || copied != sizeof(first)) return false;
        return AleInstallerEntry(first);
    }, &origin);
    return target ? (Installer)make_sym_callable((void *)target) : NULL;
#else
    return NULL;
#endif
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
        if ([dispatcher respondsToSelector:@selector(_installEventRunLoopSources:)]) {
            self.aleEventStage = @"安装事件循环·选择器";
            [dispatcher _installEventRunLoopSources:CFRunLoopGetMain()];
        } else {
            self.aleEventStage = @"解析iOS隐藏的事件循环入口";
            Installer install = ResolveInstaller();
            if (!install) { self.aleEventStage = @"未找到唯一且通过校验的事件循环入口"; return NO; }
            self.aleEventStage = @"安装事件循环·UIKit内部入口";
            install(dispatcher, @selector(_installEventRunLoopSources:), CFRunLoopGetMain());
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
        self.aleEventStage = @"事件分发初始化完成";
    } @catch (NSException *e) {
        self.aleEventStage = [self.aleEventStage stringByAppendingString:@"：接口调用异常"];
        self.aleEventsReady = NO;
    }
    return self.aleEventsReady;
}
@end
