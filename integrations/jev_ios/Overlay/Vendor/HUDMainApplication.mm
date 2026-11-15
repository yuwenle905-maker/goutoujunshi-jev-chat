// Adapted from TrollSpeed, Copyright (c) 2023 Lessica, MIT (see LICENSE).
// Ale: initialize after singleton registration. When UIKit hides its installer,
// our AX events use TSEventFetcher's own CFRunLoopSource, verified by a live probe.
#import <notify.h>
#import <objc/runtime.h>
#import "UIEventFetcher.h"
#import "UIEventDispatcher.h"
#import "HUDMainApplication.h"

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
            // No guessing instruction addresses. TSEventFetcher installs its own
            // source in common runloop modes and wakes the main loop explicitly.
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
