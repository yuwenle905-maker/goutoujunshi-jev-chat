#import "TouchBurstProbe.h"
#import "Bridge.h"
void AleProbeProgress(NSString *stage) {
    NSURL *folder = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSData *data = [NSJSONSerialization dataWithJSONObject:@{@"stage":stage} options:0 error:nil];
    [data writeToURL:[folder URLByAppendingPathComponent:@"event-progress.json"] atomically:YES];
}

@interface BurstTarget : NSObject
@property NSUInteger taps;
@property NSUInteger pans;
- (void)tap;
- (void)pan:(UIPanGestureRecognizer *)pan;
@end
@implementation BurstTarget
- (void)tap { self.taps += 1; }
- (void)pan:(UIPanGestureRecognizer *)pan {
    if (pan.state == UIGestureRecognizerStateBegan || pan.state == UIGestureRecognizerStateChanged) {
        self.pans += 1;
        CGPoint delta = [pan translationInView:pan.view.superview];
        pan.view.center = CGPointMake(pan.view.center.x + delta.x, pan.view.center.y + delta.y);
        [pan setTranslation:CGPointZero inView:pan.view.superview];
    }
}
@end

void AleProbeTouchBurst(UIWindow *window, void (^completion)(BOOL, NSDictionary *)) {
    AleProbeProgress(@"burst_start");
    BurstTarget *target = [BurstTarget new];
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    button.frame = CGRectMake(45, 420, 100, 50);
    [button setTitle:@"Burst target" forState:UIControlStateNormal];
    [button addTarget:target action:@selector(tap) forControlEvents:UIControlEventTouchUpInside];
    [window.rootViewController.view addSubview:button];
    UIView *drag = [[UIView alloc] initWithFrame:CGRectMake(170, 420, 64, 64)];
    drag.backgroundColor = UIColor.systemGreenColor;
    [drag addGestureRecognizer:[[UIPanGestureRecognizer alloc] initWithTarget:target action:@selector(pan:)]];
    [window.rootViewController.view addSubview:drag];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 100 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        CGPoint point = [button convertPoint:CGPointMake(50,25) toView:window];
        button.enabled = NO;
        AleProbeProgress(@"disabled_pair");
        AleRouteTouch(window, point, 90, UITouchPhaseBegan);
        AleRouteTouch(window, point, 90, UITouchPhaseEnded);
        BOOL disabledRejected = target.taps == 0;
        button.enabled = YES;
        AleProbeProgress(@"enabled_pairs");
        // No artificial pause between down/up. Each pair arrives in one turn,
        // as can happen when the hardware callback's main queue is backlogged.
        for (int i = 0; i < 3; ++i) {
            AleRouteTouch(window, point, 90, UITouchPhaseBegan);
            AleRouteTouch(window, point, 90, UITouchPhaseBegan); // duplicate must not create a second tap
            AleRouteTouch(window, point, 90, UITouchPhaseEnded);
            AleRouteTouch(window, point, 90, UITouchPhaseEnded);
        }
        NSUInteger before = AleAcceptedTouchFrames();
        AleProbeProgress(@"outside_controls");
        AleRouteTouch(window, CGPointZero, 91, UITouchPhaseBegan);
        AleRouteTouch(window, point, 91, UITouchPhaseMoved);
        AleRouteTouch(window, point, 91, UITouchPhaseEnded);
        AleRouteTouch(window, point, 0, UITouchPhaseBegan);
        BOOL outsideRejected = before == AleAcceptedTouchFrames();
        CGPoint start = drag.center;
        AleProbeProgress(@"pan_sequence");
        AleRouteTouch(window, start, 92, UITouchPhaseBegan);
        for (int i = 1; i <= 10; ++i)
            AleRouteTouch(window, CGPointMake(start.x + i*6, start.y + i*2), 92, UITouchPhaseMoved);
        AleRouteTouch(window, CGPointMake(start.x+60,start.y+20), 92, UITouchPhaseEnded);
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 120 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
            BOOL moved = target.pans > 0 && drag.center.x > start.x + 20;
            AleProbeProgress(@"burst_completed");
            BOOL passed = disabledRejected && outsideRejected && target.taps == 3 && moved;
            NSDictionary *result = @{@"passed":@(passed), @"rapid_tap_actions":@(target.taps),
                @"disabled_rejected":@(disabledRejected), @"outside_and_orphan_rejected":@(outsideRejected),
                @"pan_actions":@(target.pans), @"pan_moved_view":@(moved),
                @"hardware_event_capture_tested":@NO};
            [button removeFromSuperview]; [drag removeFromSuperview]; completion(passed, result);
        });
    });
}
