// Adapted from TrollSpeed, Copyright (c) 2023 Lessica, MIT (see LICENSE).
// Ale modification: fail closed if UIKit event dispatch interfaces differ;
// do not scan or call instruction addresses in UIApplication's implementation.
#import <notify.h>
#import <objc/runtime.h>
#import "UIEventFetcher.h"
#import "UIEventDispatcher.h"
#import "HUDMainApplication.h"

@interface HUDMainApplication ()
@property (nonatomic, readwrite) BOOL aleEventsReady;
@end

@implementation HUDMainApplication
- (instancetype)init {
    if ((self = [super init])) {
        int token;
        notify_register_dispatch(NOTIFY_DISMISSAL_HUD, &token, dispatch_get_main_queue(), ^(int t) {
            notify_cancel(t); exit(0);
        });
        @try {
            UIEventDispatcher *dispatcher = [self valueForKey:@"eventDispatcher"];
            if (!dispatcher || ![dispatcher respondsToSelector:@selector(_installEventRunLoopSources:)]) return self;
            [dispatcher _installEventRunLoopSources:CFRunLoopGetMain()];
            UIEventFetcher *fetcher = [[NSClassFromString(@"UIEventFetcher") alloc] init];
            if (!fetcher) return self;
            [dispatcher setValue:fetcher forKey:@"eventFetcher"];
            if ([fetcher respondsToSelector:@selector(setEventFetcherSink:)]) [fetcher setEventFetcherSink:dispatcher];
            else [fetcher setValue:dispatcher forKey:@"eventFetcherSink"];
            [self setValue:fetcher forKey:@"eventFetcher"];
            self.aleEventsReady = YES;
        } @catch (NSException *e) {
            self.aleEventsReady = NO;
        }
    }
    return self;
}
@end
