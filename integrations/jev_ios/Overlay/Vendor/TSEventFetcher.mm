//
//  TSEventFetcher.mm
//  TrollSpeed
//
//  Created by Lessica on 2024/1/24.
//

#import <dlfcn.h>
#import <string.h>
#import <CoreFoundation/CoreFoundation.h>
#import "TSEventFetcher.h"
#import "UIEvent+Private.h"
#import "UITouch-KIFAdditions.h"
#import "UIApplication+Private.h"

@interface UIEvent (AleOwnTouchEvent)
- (instancetype)_init;
- (void)_setTimestamp:(NSTimeInterval)timestamp;
- (void)_setHIDEvent:(IOHIDEventRef)event;
@end
@interface UITouch (AleHIDRefresh)
- (void)kif_setHidEvent;
@end

static NSArray *_safeTouchAry = nil;
static NSMutableArray *_touchAry = nil;
static NSMutableArray *_livingTouchAry = nil;
static CFRunLoopSourceRef _source = NULL;
static NSString *_failure = @"";
static __weak UIWindow *_deliveryWindow = nil;
static NSUInteger _deliveryCount = 0;
static UIEvent *_ownedEvent = nil;
static BOOL _useWindowRoute = NO;
static int _stageCode = 0;
#define ALE_STAGE(n) __atomic_store_n(&_stageCode, n, __ATOMIC_RELAXED)

static UITouch *toRemove = nil;
static UITouch *toStationarify = nil;

static void __TSEventFetcherCallback(void *info)
{
 IOHIDEventRef deliveryHID = NULL;
 @try {
  ALE_STAGE(1);
  static UIApplication *app = [UIApplication sharedApplication];
  // _touchesEvent can remain nil before the first hardware touch. Create our
  // own UITouchesEvent instead of depending on UIApplication's cached event.
  if (!_ownedEvent) {
    Class type = NSClassFromString(@"UITouchesEvent");
    if (type && [type isSubclassOfClass:UIEvent.class] && [type instancesRespondToSelector:@selector(_init)]) {
      ALE_STAGE(2); _ownedEvent = [[type alloc] _init];
    }
  }
  UIEvent *event = _ownedEvent;
  if (!event && [app respondsToSelector:@selector(_touchesEvent)]) event = [app _touchesEvent];
  if (!event) { _failure = @"UIKit未创建触摸事件对象"; return; }
  
  // to retain objects from being released
  ALE_STAGE(3); [event _clearTouches];
  if ([event respondsToSelector:@selector(_setTimestamp:)]) [event _setTimestamp:NSProcessInfo.processInfo.systemUptime];

  NSArray *myAry = _safeTouchAry;
  for (UITouch *aTouch in myAry)
  {
    ALE_STAGE(4);
    [aTouch kif_setHidEvent];
    switch (aTouch.phase) {
    case UITouchPhaseEnded:
    case UITouchPhaseCancelled:
      toRemove = aTouch;
      break;
    case UITouchPhaseBegan:
      toStationarify = aTouch;
      break;
    default:
      break;
    }

    [event _addTouch:aTouch forDelayedDelivery:NO];
  }

  if (myAry.count && [event respondsToSelector:@selector(_setHIDEvent:)]) {
    ALE_STAGE(5);
    deliveryHID = kif_IOHIDEventWithTouches(myAry);
    if (!deliveryHID) { _failure = @"无法创建当前触摸的HID数据"; return; }
    [event _setHIDEvent:deliveryHID];
  }

  // All touches belong to our single HUD window. Deliver through UIWindow's
  // public dispatcher, without UIApplication's hidden event-loop installer.
  UIWindow *window = _deliveryWindow;
  if (!window) { _failure = @"悬浮触摸目标窗口已释放"; return; }
  ALE_STAGE(6);
  if (_useWindowRoute) [window sendEvent:event];
  else [app sendEvent:event];
  _deliveryCount += 1;
  ALE_STAGE(7);
 } @catch (NSException *exception) { ALE_STAGE(8); _failure = @"UIKit内部事件派发异常"; }
 @finally { if (deliveryHID) CFRelease(deliveryHID); }
}

@implementation TSEventFetcher
+ (NSString *)lastFailure { return _failure; }
+ (NSUInteger)deliveryCount { return _deliveryCount; }
+ (void)useWindowRoute:(BOOL)enabled { _useWindowRoute = enabled; }
+ (void)resetFailure { _failure = @""; }
+ (NSString *)deliveryStage {
    switch (__atomic_load_n(&_stageCode, __ATOMIC_RELAXED)) {
        case 1:return @"获取事件类型"; case 2:return @"初始化事件对象";
        case 3:return @"清理事件容器"; case 4:return @"刷新触摸数据";
        case 5:return @"刷新HID数据"; case 6:return @"进入事件派发";
        case 7:return @"事件派发已返回"; case 8:return @"事件派发异常";
        default:return @"尚未派发";
    }
}

+ (void)initialize
{
  if (self != [TSEventFetcher class]) return;
  _livingTouchAry = [[NSMutableArray alloc] init];
  _touchAry = [[NSMutableArray alloc] init];
  
  for (NSInteger i = 0; i < 100; i++)
  {
    UITouch *touch = [[UITouch alloc] init];
    [touch setPhaseAndUpdateTimestamp:UITouchPhaseEnded];
    [_touchAry addObject:touch];
  }

  CFRunLoopSourceContext context;
  memset(&context, 0, sizeof(CFRunLoopSourceContext));
  context.perform = __TSEventFetcherCallback;
  
  // content of context is copied
  _source = CFRunLoopSourceCreate(kCFAllocatorDefault, -2, &context);
  CFRunLoopRef loop = CFRunLoopGetMain();
  CFRunLoopAddSource(loop, _source, kCFRunLoopCommonModes);
}

+ (NSInteger)receiveAXEventID:(NSInteger)eventId
           atGlobalCoordinate:(CGPoint)coordinate
               withTouchPhase:(UITouchPhase)phase
                     inWindow:(UIWindow *)window
                       onView:(UIView *)view
{
  if (!window || eventId < 1 || eventId > 100) { _failure = @"悬浮触摸参数无效"; return 0; }
  _deliveryWindow = window;
  BOOL deleted = NO;
  UITouch *touch = nil;
  BOOL needsCopy = NO;

  if (toRemove != nil)
  {
    touch = toRemove;
    toRemove = nil;
    [_livingTouchAry removeObjectIdenticalTo:touch];
    deleted = YES;
    needsCopy = YES;
  }

  if (toStationarify != nil)
  {
    // in case this is changed during the operations
    touch = toStationarify;
    toStationarify = nil;
    if (touch.phase == UITouchPhaseBegan)
      [touch setPhaseAndUpdateTimestamp:UITouchPhaseStationary];
  }

  eventId -= 1;

  // ideally should be phase began when this hit
  // but if by any means other phases come... well lets be forgiving
  touch = _touchAry[eventId];
  BOOL oldState = [_livingTouchAry containsObject:touch];
  BOOL newState = !oldState;
  if (newState)
  {
    if (phase == UITouchPhaseEnded || phase == UITouchPhaseCancelled)
      return deleted;
    touch = [[UITouch alloc] initAtPoint:coordinate inWindow:window onView:view];
    [_livingTouchAry addObject:touch];
    [_touchAry setObject:touch atIndexedSubscript:eventId];
    needsCopy = YES;
  }
  else
  {
    if (touch.phase == UITouchPhaseBegan && phase == UITouchPhaseMoved)
      return deleted;
    [touch setLocationInWindow:coordinate];
  }

  [touch setPhaseAndUpdateTimestamp:phase];
  
  if (needsCopy)
  {
    CFTypeRef delayRelease = CFBridgingRetain(_safeTouchAry);
    _safeTouchAry = [[NSArray alloc] initWithArray:_livingTouchAry copyItems:NO];
    CFBridgingRelease(delayRelease);
  }

  CFRunLoopSourceSignal(_source);
  CFRunLoopWakeUp(CFRunLoopGetMain());
  return deleted;
}

@end
