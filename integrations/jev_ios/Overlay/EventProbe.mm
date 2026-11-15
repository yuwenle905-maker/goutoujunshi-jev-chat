#import "Bridge.h"
#import "TSEventFetcher.h"

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
    __block NSString *failure = nil;
    [button addAction:[UIAction actionWithHandler:^(__kindof UIAction *action) { count += 1; }]
       forControlEvents:UIControlEventTouchUpInside];
    [root addSubview:button];
    [root layoutIfNeeded];
    CGPoint point = [button convertPoint:CGPointMake(8, 8) toView:window];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 100 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        @try {
            [TSEventFetcher receiveAXEventID:99 atGlobalCoordinate:point withTouchPhase:UITouchPhaseBegan inWindow:window onView:button];
        } @catch (NSException *exception) { failure = @"自检触摸开始接口异常"; }
    });
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 280 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        @try {
            [TSEventFetcher receiveAXEventID:99 atGlobalCoordinate:point withTouchPhase:UITouchPhaseEnded inWindow:window onView:button];
        } @catch (NSException *exception) { failure = @"自检触摸结束接口异常"; }
    });
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 650 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        [button removeFromSuperview];
        BOOL passed = !failure && count == 1;
        NSString *sourceFailure = [TSEventFetcher lastFailure];
        completion(passed, failure ?: (sourceFailure.length ? sourceFailure : [NSString stringWithFormat:@"按钮实际动作次数：%ld", (long)count]));
    });
}
