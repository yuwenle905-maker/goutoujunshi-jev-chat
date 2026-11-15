#import "Bridge.h"
#import "TSEventFetcher.h"

static void WaitForDelivery(NSUInteger previous, CFAbsoluteTime deadline, void (^completion)(BOOL)) {
    if ([TSEventFetcher deliveryCount] > previous) { completion(YES); return; }
    if (CFAbsoluteTimeGetCurrent() >= deadline) { completion(NO); return; }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 20 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        WaitForDelivery(previous, deadline, completion);
    });
}

// A real UIControl action delivered by the production UITouch/event source.
// No sendActionsForControlEvents, direct callback invocation or host-app input.
void AleProbeWindow(UIWindow *window, BOOL enabled, void (^completion)(BOOL, NSString *)) {
    UIView *root = window.rootViewController.view;
    if (!root || window.hidden) { completion(NO, @"自检窗口未就绪"); return; }
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    button.frame = CGRectMake(12, 110, 16, 16);
    button.alpha = 0.02;
    button.accessibilityElementsHidden = YES;
    button.enabled = enabled;
    __block NSInteger count = 0;
    [button addAction:[UIAction actionWithHandler:^(__kindof UIAction *action) { count += 1; }]
       forControlEvents:UIControlEventTouchUpInside];
    [root addSubview:button];
    [root layoutIfNeeded];
    CGPoint point = [button convertPoint:CGPointMake(8, 8) toView:window];
    void (^finish)(NSString *) = ^(NSString *failure) {
        [button removeFromSuperview];
        NSString *sourceFailure = [TSEventFetcher lastFailure];
        BOOL passed = !failure && !sourceFailure.length && count == 1;
        completion(passed, failure ?: (sourceFailure.length ? sourceFailure : [NSString stringWithFormat:@"按钮实际动作次数：%ld", (long)count]));
    };
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 100 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        NSUInteger before = [TSEventFetcher deliveryCount];
        @try {
            [TSEventFetcher receiveAXEventID:99 atGlobalCoordinate:point withTouchPhase:UITouchPhaseBegan inWindow:window onView:button];
        } @catch (NSException *exception) { finish(@"自检触摸开始接口异常"); return; }
        WaitForDelivery(before, CFAbsoluteTimeGetCurrent() + 2, ^(BOOL delivered) {
            if (!delivered) { finish(@"独立事件源未完成按下派发"); return; }
            // Wait for actual delivery, rather than scheduling down/up at fixed
            // wall times that can coalesce under a cold SwiftUI layout.
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
                NSUInteger beforeUp = [TSEventFetcher deliveryCount];
                @try {
                    [TSEventFetcher receiveAXEventID:99 atGlobalCoordinate:point withTouchPhase:UITouchPhaseEnded inWindow:window onView:button];
                } @catch (NSException *exception) { finish(@"自检触摸结束接口异常"); return; }
                WaitForDelivery(beforeUp, CFAbsoluteTimeGetCurrent() + 2, ^(BOOL ended) {
                    if (!ended) { finish(@"独立事件源未完成抬起派发"); return; }
                    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{ finish(nil); });
                });
            });
        });
    });
}
