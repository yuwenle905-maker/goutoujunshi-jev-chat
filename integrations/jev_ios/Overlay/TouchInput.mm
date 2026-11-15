#import "Bridge.h"
#import "TSEventFetcher.h"
#import <math.h>

// Main-thread routing of immutable hardware frames. Only gestures beginning
// on our controls are forwarded; a finger outside the HUD is never adopted.
static BOOL active[99];
static NSUInteger accepted = 0;
BOOL AleRouteTouch(UIWindow *window, CGPoint point, NSInteger pointer, UITouchPhase phase) {
    NSCAssert(NSThread.isMainThread, @"HUD input must run on the main thread");
    if (!window || window.hidden || pointer < 1 || pointer > 98 || !isfinite(point.x) || !isfinite(point.y)) return NO;
    UIView *hit = [window hitTest:point withEvent:nil];
    if (phase == UITouchPhaseBegan) {
        if (active[pointer] || !hit || hit == window || hit == window.rootViewController.view) return NO;
        active[pointer] = YES;
    } else if (!active[pointer]) return NO;
    if (phase == UITouchPhaseEnded || phase == UITouchPhaseCancelled) active[pointer] = NO;
    [TSEventFetcher receiveAXEventID:pointer atGlobalCoordinate:point withTouchPhase:phase inWindow:window onView:hit];
    // A source signal alone coalesces down/up frames arriving in one main-queue
    // drain. Flush each frame before the following frame mutates its UITouch.
    [TSEventFetcher flushPendingEvents];
    accepted += 1;
    return YES;
}
NSUInteger AleAcceptedTouchFrames(void) { return accepted; }
