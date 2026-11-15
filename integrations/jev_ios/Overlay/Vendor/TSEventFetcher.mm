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

static NSArray *_safeTouchAry = nil;
static NSMutableArray *_touchAry = nil;
static NSMutableArray *_livingTouchAry = nil;
static CFRunLoopSourceRef _source = NULL;
static NSString *_failure = @"";
static __weak UIWindow *_deliveryWindow = nil;

static UITouch *toRemove = nil;
static UITouch *toStationarify = nil;

static void __TSEventFetcherCallback(void *info)
{
 @try {
  static UIApplication *app = [UIApplication sharedApplication];
  if (![app respondsToSelector:@selector(_touchesEvent)]) { _failure = @"UIKit缺少触摸事件接口"; return; }
  UIEvent *event = [app _touchesEvent];
  if (!event) { _failure = @"UIKit未创建触摸事件对象"; return; }
  
  // to retain objects from being released
  [event _clearTouches];

  NSArray *myAry = _safeTouchAry;
  for (UITouch *aTouch in myAry)
  {
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

  // All touches belong to our single HUD window. Deliver through UIWindow's
  // public dispatcher, without UIApplication's hidden event-loop installer.
  UIWindow *window = _deliveryWindow;
  if (!window) { _failure = @"悬浮触摸目标窗口已释放"; return; }
  [window sendEvent:event];
 } @catch (NSException *exception) { _failure = @"UIKit内部事件派发异常"; }
}

@implementation TSEventFetcher
+ (NSString *)lastFailure { return _failure; }

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
