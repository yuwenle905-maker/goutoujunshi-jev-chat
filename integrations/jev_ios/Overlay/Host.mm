// Independent HUD bootstrap; hosting/event integration follows MIT TrollSpeed.
// No injection into SpringBoard or a chat app. All forwarded touches terminate
// at this process's own views; this code never clicks or types into other apps.
#import "Bridge.h"
#import <dlfcn.h>
#import <objc/runtime.h>
#import <IOSurface/IOSurface.h>
#import "BackboardServices.h"
#import "UIApplication+Private.h"
#import "AXEventRepresentation.h"
#import "TSEventFetcher.h"

BOOL AleHostWindow(UIWindow *window) {
    id host = [[NSClassFromString(@"SBSAccessibilityWindowHostingController") alloc] init];
    SEL selector = NSSelectorFromString(@"registerWindowWithContextID:atLevel:");
    SEL contextSelector = NSSelectorFromString(@"_contextId");
    if (!host || ![host respondsToSelector:selector] || ![window respondsToSelector:contextSelector]) return NO;
    uint32_t context = ((uint32_t(*)(id, SEL))[window methodForSelector:contextSelector])(window, contextSelector);
    if (!context) return NO;
    double level = window.windowLevel;
    NSInvocation *call = [NSInvocation invocationWithMethodSignature:[NSMethodSignature signatureWithObjCTypes:"v@:Id"]];
    call.target = host; call.selector = selector;
    [call setArgument:&context atIndex:2]; [call setArgument:&level atIndex:3];
    [call invoke];
    objc_setAssociatedObject(window, @selector(AleHostWindow:), host, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    return YES;
}

static void Event(void *, void *, IOHIDServiceRef, IOHIDEventRef event) {
    static Class repClass;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        [[NSBundle bundleWithPath:@"/System/Library/PrivateFrameworks/AccessibilityUtilities.framework"] load];
        repClass = NSClassFromString(@"AXEventRepresentation");
    });
    if (!repClass) return;
    AXEventRepresentation *rep = [repClass representationWithHIDEvent:event hidStreamIdentifier:@"UIApplicationEvents"];
    dispatch_async(dispatch_get_main_queue(), ^{
        UIWindow *window = UIApplication.sharedApplication.windows.firstObject;
        if (!window || window.hidden) return;
        UIView *hit = [window hitTest:rep.location withEvent:nil];
        // Preserve move/end for an existing gesture even after leaving its view.
        if (!hit && [rep isTouchDown]) return;
        UITouchPhase phase = [rep isTouchDown] ? UITouchPhaseBegan :
            [rep isMove] ? UITouchPhaseMoved : [rep isCancel] ? UITouchPhaseCancelled : UITouchPhaseEnded;
        NSInteger pointer = [[rep.handInfo.paths firstObject] pathIdentity];
        if (pointer < 1 || pointer > 98) return;
        [TSEventFetcher receiveAXEventID:pointer atGlobalCoordinate:rep.location withTouchPhase:phase inWindow:window onView:hit];
    });
}

int AleRunHUD(void) {
    @autoreleasepool {
        // Resolve startup symbols first. A missing private interface is an
        // explicit unsupported result, never an instruction to alter the OS.
        void *backboard = dlopen("/System/Library/PrivateFrameworks/BackBoardServices.framework/BackBoardServices", RTLD_NOW);
        void *graphics = dlopen("/System/Library/PrivateFrameworks/GraphicsServices.framework/GraphicsServices", RTLD_NOW);
        dlopen("/System/Library/PrivateFrameworks/SpringBoardServices.framework/SpringBoardServices", RTLD_NOW);
        auto singleton = (void(*)(Class))dlsym(RTLD_DEFAULT, "UIApplicationInstantiateSingleton");
        auto initialize = (void(*)(void))dlsym(RTLD_DEFAULT, "UIApplicationInitialize");
        auto display = (void(*)(void))dlsym(backboard ?: RTLD_DEFAULT, "BKSDisplayServicesStart");
        auto gs = (void(*)(void))dlsym(graphics ?: RTLD_DEFAULT, "GSInitialize");
        auto events = (void*(*)(void(*)(void*,void*,IOHIDServiceRef,IOHIDEventRef)))dlsym(backboard ?: RTLD_DEFAULT, "BKSHIDEventRegisterEventCallback");
        if (!singleton || !initialize || !display || !gs || !events || !NSClassFromString(@"SBSAccessibilityWindowHostingController")) return 70;
        [UIScreen initialize]; CFRunLoopGetCurrent(); gs(); display(); initialize();
        singleton(NSClassFromString(@"HUDMainApplication"));
        id<UIApplicationDelegate> delegate = [[NSClassFromString(@"AleHUDDelegate") alloc] init];
        UIApplication *app = UIApplication.sharedApplication;
        app.delegate = delegate;
        if (![app respondsToSelector:@selector(__completeAndRunAsPlugin)]) return 71;
        [app _accessibilityInit];
        events(Event);
        auto eventInitialize = (void(*)(Boolean))dlsym(graphics ?: RTLD_DEFAULT, "GSEventInitialize");
        auto pushMode = (void(*)(CFStringRef))dlsym(graphics ?: RTLD_DEFAULT, "GSEventPushRunLoopMode");
        if (eventInitialize) eventInitialize(false);
        if (pushMode) pushMode(kCFRunLoopDefaultMode);
        [app __completeAndRunAsPlugin];
        CFRunLoopRun();
        return 0;
    }
}

UIImage *AleScreenImage(void) {
    // Render only on an explicit tap, after hiding our windows. Secure surfaces
    // may be black and are never bypassed. The image remains local for Vision.
    typedef void (*Render)(mach_port_t, CFStringRef, IOSurfaceRef, uint32_t, uint32_t);
    Render render = (Render)dlsym(RTLD_DEFAULT, "CARenderServerRenderDisplay");
    if (!render) return nil;
    CGSize size = UIScreen.mainScreen.bounds.size;
    CGFloat scale = MIN(UIScreen.mainScreen.scale, 2.0);
    size_t width = (size_t)(size.width * scale), height = (size_t)(size.height * scale);
    if (!width || !height || width * height > 8000000) return nil;
    size_t row = IOSurfaceAlignProperty(kIOSurfaceBytesPerRow, width * 4);
    NSDictionary *props = @{(id)kIOSurfaceWidth:@(width), (id)kIOSurfaceHeight:@(height),
        (id)kIOSurfaceBytesPerElement:@4, (id)kIOSurfaceBytesPerRow:@(row),
        (id)kIOSurfaceAllocSize:@(row * height), (id)kIOSurfacePixelFormat:@(0x42475241)};
    IOSurfaceRef surface = IOSurfaceCreate((__bridge CFDictionaryRef)props);
    if (!surface) return nil;
    IOSurfaceLock(surface, 0, NULL);
    render(MACH_PORT_NULL, CFSTR("LCD"), surface, 0, 0);
    CGColorSpaceRef color = CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx = CGBitmapContextCreate(IOSurfaceGetBaseAddress(surface), width, height, 8, row, color,
        kCGBitmapByteOrder32Little | kCGImageAlphaPremultipliedFirst);
    CGImageRef image = ctx ? CGBitmapContextCreateImage(ctx) : NULL;
    UIImage *result = image ? [UIImage imageWithCGImage:image scale:scale orientation:UIImageOrientationUp] : nil;
    if (image) CGImageRelease(image);
    if (ctx) CGContextRelease(ctx);
    CGColorSpaceRelease(color); IOSurfaceUnlock(surface, 0, NULL); CFRelease(surface);
    return result;
}
