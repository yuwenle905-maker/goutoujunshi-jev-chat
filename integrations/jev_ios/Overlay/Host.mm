// Independent HUD bootstrap; hosting/event integration follows MIT TrollSpeed.
// No injection into SpringBoard or a chat app. All forwarded touches terminate
// at this process's own views; this code never clicks or types into other apps.
#import "Bridge.h"
#import <dlfcn.h>
#import <objc/runtime.h>
#import "BackboardServices.h"
#import "UIApplication+Private.h"
#import "AXEventRepresentation.h"
#import "TSEventFetcher.h"
#import "HUDMainApplication.h"
static __weak UIWindow *s_window;
NSString *AleEventFailure(void) {
    UIApplication *app = UIApplication.sharedApplication;
    return [app isKindOfClass:HUDMainApplication.class] ? [(HUDMainApplication *)app aleEventStage] : @"UIApplication类型不符";
}

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
    s_window = window;
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
        UIWindow *window = s_window;
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
        static id<UIApplicationDelegate> delegate;
        delegate = [[NSClassFromString(@"AleHUDDelegate") alloc] init];
        UIApplication *app = UIApplication.sharedApplication;
        app.delegate = delegate;
        if (![app respondsToSelector:@selector(__completeAndRunAsPlugin)]) return 71;
        [app _accessibilityInit];
        events(Event);
        auto eventInitialize = (void(*)(Boolean))dlsym(graphics ?: RTLD_DEFAULT, "GSEventInitialize");
        auto pushMode = (void(*)(CFStringRef))dlsym(graphics ?: RTLD_DEFAULT, "GSEventPushRunLoopMode");
        if (eventInitialize) eventInitialize(false);
        if (pushMode) pushMode(kCFRunLoopDefaultMode);
        if (![(HUDMainApplication *)app prepareAleEvents]) return 73;
        @try { [app __completeAndRunAsPlugin]; }
        @catch (NSException *exception) { return 74; }
        CFRunLoopRun();
        return 0;
    }
}

UIImage *AleScreenImage(void) {
    // Render only on an explicit tap, after hiding our windows. Secure surfaces
    // may be black and are never bypassed. The image remains local for Vision.
    typedef CFTypeRef Surface;
    typedef void (*Render)(mach_port_t, CFStringRef, Surface, uint32_t, uint32_t);
    Render render = (Render)dlsym(RTLD_DEFAULT, "CARenderServerRenderDisplay");
    void *io = dlopen("/System/Library/Frameworks/IOSurface.framework/IOSurface", RTLD_NOW);
    if (!io) io = dlopen("/System/Library/PrivateFrameworks/IOSurface.framework/IOSurface", RTLD_NOW);
    if (!render || !io) return nil;
    auto create = (Surface(*)(CFDictionaryRef))dlsym(io, "IOSurfaceCreate");
    auto lock = (int(*)(Surface,uint32_t,uint32_t*))dlsym(io, "IOSurfaceLock");
    auto unlock = (int(*)(Surface,uint32_t,uint32_t*))dlsym(io, "IOSurfaceUnlock");
    auto address = (void*(*)(Surface))dlsym(io, "IOSurfaceGetBaseAddress");
    if (!create || !lock || !unlock || !address) return nil;
    CGSize size = UIScreen.mainScreen.bounds.size;
    CGFloat scale = MIN(UIScreen.mainScreen.scale, 2.0);
    size_t width = (size_t)(size.width * scale), height = (size_t)(size.height * scale);
    if (!width || !height || width * height > 8000000) return nil;
    size_t row = (width * 4 + 63) & ~((size_t)63);
    NSDictionary *props = @{@"IOSurfaceWidth":@(width), @"IOSurfaceHeight":@(height),
        @"IOSurfaceBytesPerElement":@4, @"IOSurfaceBytesPerRow":@(row),
        @"IOSurfaceAllocSize":@(row * height), @"IOSurfacePixelFormat":@(0x42475241)};
    Surface surface = create((__bridge CFDictionaryRef)props);
    if (!surface) return nil;
    if (lock(surface, 0, NULL) != 0) { CFRelease(surface); return nil; }
    render(MACH_PORT_NULL, CFSTR("LCD"), surface, 0, 0);
    CGColorSpaceRef color = CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx = CGBitmapContextCreate(address(surface), width, height, 8, row, color,
        kCGBitmapByteOrder32Little | kCGImageAlphaPremultipliedFirst);
    CGImageRef image = ctx ? CGBitmapContextCreateImage(ctx) : NULL;
    UIImage *result = image ? [UIImage imageWithCGImage:image scale:scale orientation:UIImageOrientationUp] : nil;
    if (image) CGImageRelease(image);
    if (ctx) CGContextRelease(ctx);
    CGColorSpaceRelease(color); unlock(surface, 0, NULL); CFRelease(surface);
    return result;
}
