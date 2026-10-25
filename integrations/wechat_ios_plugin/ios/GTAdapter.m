#import "GT.h"

// Public historical examples use these names. They have NOT been verified on 8.0.75.
// All private calls are confined to this file. Never substitute selector guesses at runtime.
BOOL GTObjectMethod(Class cls, SEL sel, NSUInteger count, BOOL returnsVoid) {
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) return NO;
    NSMethodSignature *s = [NSMethodSignature signatureWithObjCTypes:method_getTypeEncoding(m)];
    if (s.numberOfArguments != count + 2 || (returnsVoid ? s.methodReturnType[0] != 'v' : s.methodReturnType[0] != '@')) return NO;
    for (NSUInteger i = 2; i < s.numberOfArguments; i++) if ([s getArgumentTypeAtIndex:i][0] != '@' && [s getArgumentTypeAtIndex:i][0] != '#') return NO;
    return YES;
}
id GTCall(id object, NSString *selector, NSArray *args) {
    SEL sel = NSSelectorFromString(selector);
    if (!object || !GTObjectMethod(object_getClass(object), sel, args.count, NO)) return nil;
    NSMethodSignature *s = [object methodSignatureForSelector:sel];
    NSInvocation *inv = [NSInvocation invocationWithMethodSignature:s];
    inv.target = object; inv.selector = sel;
    for (NSUInteger i = 0; i < args.count; i++) { id arg = args[i]; [inv setArgument:&arg atIndex:i + 2]; }
    @try { [inv invoke]; __unsafe_unretained id result = nil; [inv getReturnValue:&result]; return result; } @catch (__unused NSException *e) { GTLog(@"private_call_failed"); return nil; }
}
static id GTService(NSString *name) {
    id center = GTCall(NSClassFromString(@"MMServiceCenter"), @"defaultCenter", @[]);
    Class cls = NSClassFromString(name);
    return cls ? GTCall(center, @"getService:", @[cls]) : nil;
}
static id GTValue(id object, NSString *name) { @try { return [object valueForKey:name]; } @catch (__unused NSException *e) { return nil; } }
static NSString *GTString(id object, NSString *name) { id v = GTValue(object, name); return [v isKindOfClass:NSString.class] ? v : nil; }
static void (*GTOrigReceive)(id, SEL, id, id);
static void GTReceive(id self, SEL cmd, id session, id wrap) {
    GTOrigReceive(self, cmd, session, wrap); // Preserve host behavior, even when plugin is disabled.
    @try {
        if ([GTValue(wrap, @"m_uiMessageType") integerValue] != 1) return;
        id contact = GTCall(GTService(@"CContactMgr"), @"getSelfContact", @[]);
        NSString *account = GTString(contact, @"m_nsUsrName");
        NSString *from = GTString(wrap, @"m_nsFromUsr"), *to = GTString(wrap, @"m_nsToUsr"), *content = GTString(wrap, @"m_nsContent");
        NSString *messageID = [GTValue(wrap, @"m_n64MesSvrID") description];
        if (!account.length || !from.length || !to.length || !content.length || !messageID.longLongValue) { GTLog(@"receive_missing_identity_or_server_id"); return; }
        BOOL outgoing = [from isEqual:account];
        NSString *peer = outgoing ? to : from;
        NSDictionary *event = @{@"account":account, @"peer":peer, @"message_id":messageID, @"content":content, @"outgoing":@(outgoing)};
        dispatch_async(dispatch_get_main_queue(), ^{ [GTWXAICoordinator.shared observe:event]; });
    } @catch (__unused NSException *e) { GTLog(@"receive_decode_failed"); }
}
void GTInstallAdapter(void) {
    static BOOL installed = NO;
    NSCAssert(NSThread.isMainThread, @"Hooks must be installed on main thread");
    if (installed) return;
    if (![NSBundle.mainBundle.bundleIdentifier isEqual:@"com.tencent.xin"]) return;
    NSString *version = [NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"];
    if (![version isEqual:@"8.0.75"]) { GTLog(@"unsupported_wechat_version"); return; }
    Class cls = NSClassFromString(@"CMessageMgr"); SEL sel = NSSelectorFromString(@"AsyncOnAddMsg:MsgWrap:");
    if (!GTObjectMethod(cls, sel, 2, YES)) { GTLog(@"receive_selector_unavailable"); return; }
    Method m = class_getInstanceMethod(cls, sel);
    GTOrigReceive = (void *)method_getImplementation(m);
    // Copy inherited implementation onto this class before replacing it.
    if (!class_addMethod(cls, sel, (IMP)GTReceive, method_getTypeEncoding(m))) method_setImplementation(m, (IMP)GTReceive);
    installed = YES;
    GTLog(@"candidate_receive_hook_installed_not_device_verified");
}
BOOL GTCanSend(void) {
    if (!GT_VERIFIED_8075_SEND) return NO;
    if (![[NSBundle.mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] isEqual:@"8.0.75"]) return NO;
    return GTObjectMethod(NSClassFromString(@"CMessageMgr"), NSSelectorFromString(@"AddMsg:MsgWrap:"), 2, YES);
}
BOOL GTSubmit(NSString *account, NSString *peer, NSString *text) {
    if (!GTCanSend() || !text.length || !peer.length) return NO;
    id contact = GTCall(GTService(@"CContactMgr"), @"getSelfContact", @[]);
    if (![GTString(contact, @"m_nsUsrName") isEqual:account]) return NO;
    id manager = GTService(@"CMessageMgr"); Class cls = NSClassFromString(@"CMessageWrap");
    SEL init = NSSelectorFromString(@"initWithMsgType:");
    Method im = class_getInstanceMethod(cls, init);
    NSMethodSignature *sig = im ? [NSMethodSignature signatureWithObjCTypes:method_getTypeEncoding(im)] : nil;
    if (!manager || !sig || sig.numberOfArguments != 3 || sig.methodReturnType[0] != '@' || strcmp([sig getArgumentTypeAtIndex:2], @encode(unsigned int))) return NO;
    @try {
        id wrap = ((id (*)(id, SEL, unsigned int))objc_msgSend)([cls alloc], init, 1);
        [wrap setValue:account forKey:@"m_nsFromUsr"]; [wrap setValue:peer forKey:@"m_nsToUsr"];
        [wrap setValue:text forKey:@"m_nsContent"]; [wrap setValue:@1 forKey:@"m_uiStatus"];
        [wrap setValue:@((unsigned int)NSDate.date.timeIntervalSince1970) forKey:@"m_uiCreateTime"];
        ((void (*)(id, SEL, id, id))objc_msgSend)(manager, NSSelectorFromString(@"AddMsg:MsgWrap:"), peer, wrap);
        GTLog(@"private_send_submitted_not_delivery_confirmation"); return YES;
    } @catch (__unused NSException *e) { GTLog(@"private_send_exception_unknown_result"); return NO; }
}
