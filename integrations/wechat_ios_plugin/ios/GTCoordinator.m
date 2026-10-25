#import "GT.h"
#import <CommonCrypto/CommonDigest.h>

static NSString *GTHash(NSString *value) {
    NSData *d = [value dataUsingEncoding:NSUTF8StringEncoding]; unsigned char result[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(d.bytes, (CC_LONG)d.length, result); NSMutableString *s = [NSMutableString new];
    for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) [s appendFormat:@"%02x", result[i]]; return s;
}
static UIViewController *GTTop(void) {
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) if ([scene isKindOfClass:UIWindowScene.class] && scene.activationState == UISceneActivationStateForegroundActive) {
        for (UIWindow *w in ((UIWindowScene *)scene).windows) if (w.isKeyWindow) { UIViewController *vc = w.rootViewController; while (vc.presentedViewController) vc = vc.presentedViewController; return vc; }
    } return nil;
}
@implementation GTCoordinator
+ (instancetype)shared { static GTCoordinator *v; static dispatch_once_t once; dispatch_once(&once, ^{ v = [GTCoordinator new]; }); return v; }
- (instancetype)init {
    if ((self = [super init])) { _histories = [NSMutableDictionary new]; _revisions = [NSMutableDictionary new]; _drafts = [NSMutableDictionary new]; _seen = [NSMutableDictionary new]; _pending = [NSMutableDictionary new]; _paused = [NSMutableSet new]; }
    return self;
}
- (NSString *)scope:(NSString *)peer { return GTHash([NSString stringWithFormat:@"%@\n%@", self.account ?: @"", peer ?: @""]); }
- (void)cancel:(NSString *)peer { NSString *s = [self scope:peer]; self.revisions[s] = @([self.revisions[s] integerValue] + 1); [self.drafts removeObjectForKey:s]; GTLog(@"task_cancelled"); }
- (BOOL)allowed:(NSString *)scope {
    NSDictionary *c = GTConfig.shared.values;
    return [c[@"enabled"] boolValue] && [c[@"cloud_consent"] boolValue] && ([c[@"all_friends"] boolValue] || [[GTConfig.shared profile:scope][@"enabled"] boolValue]);
}
- (void)observe:(NSDictionary *)e {
    NSAssert(NSThread.isMainThread, @"Main queue only");
    if (self.account.length && ![self.account isEqual:e[@"account"]]) { [self.histories removeAllObjects]; [self.revisions removeAllObjects]; [self.drafts removeAllObjects]; [self.pending removeAllObjects]; }
    self.account = e[@"account"]; NSString *peer = e[@"peer"], *scope = [self scope:peer];
    BOOL outgoing = [e[@"outgoing"] boolValue];
    NSString *dedup = GTHash([NSString stringWithFormat:@"%@:%@:%@", scope, outgoing ? @"out" : @"in", e[@"message_id"]]);
    if (self.seen[dedup]) return;
    self.seen[dedup] = @YES;
    if (self.seen.count > 2000) { [self.seen removeAllObjects]; self.seen[dedup] = @YES; }
    if (outgoing && [self.pending[scope][@"text"] isEqual:e[@"content"]]) {
        // A local echo is not a server-delivery receipt.
        NSMutableDictionary *ledger = GTConfig.shared.values[@"ledger"];
        ledger[self.pending[scope][@"key"]] = @"local_echo"; [GTConfig.shared save];
        [GTConfig.shared.values[@"blocked"] removeObjectForKey:scope]; [GTConfig.shared save];
        [self.pending removeObjectForKey:scope]; GTLog(@"local_echo_observed_delivery_not_proven");
    }
    [self cancel:peer]; // A manual reply invalidates stale generation but never permanently pauses the peer.
    NSMutableArray *history = self.histories[scope];
    if (!history) self.histories[scope] = history = [NSMutableArray new];
    if (history.count >= 40) [history removeObjectAtIndex:0];
    // Bound context payload; full content is not written to disk.
    NSString *content = e[@"content"];
    if (content.length > 2000) { GTLog(@"message_too_long_manual_only"); return; }
    [history addObject:@{@"role":outgoing ? @"me" : @"peer", @"content":content}];
    if (outgoing || ![self allowed:scope] || [self.paused containsObject:scope] || GTConfig.shared.values[@"blocked"][scope]) return;
    // Existing unresolved submissions persist across launches; never blind-retry.
    NSString *key = GTHash([NSString stringWithFormat:@"%@:%@", scope, e[@"message_id"]]);
    if (GTConfig.shared.values[@"ledger"][key]) { GTLog(@"duplicate_or_unknown_submission_blocked"); return; }
    NSDictionary *cfg = GTConfig.shared.values;
    BOOL group = [peer hasSuffix:@"@chatroom"];
    if (group && (![cfg[@"groups"] boolValue] || ![cfg[@"group_without_at"] boolValue])) { GTLog(@"group_requires_structured_mention_adapter"); return; }
    NSInteger revision = [self.revisions[scope] integerValue];
    NSMutableDictionary *profile = [[GTConfig.shared profile:scope] mutableCopy];
    if (![profile[@"persona"] length]) profile[@"persona"] = cfg[@"persona"];
    profile[@"prefix"] = cfg[@"prefix"]; profile[@"suffix"] = cfg[@"suffix"];
    profile[@"meme_bank"] = cfg[@"meme_bank"] ?: @"";
    NSArray *examples = profile[@"examples"] ?: @[]; [profile removeObjectForKey:@"examples"];
    NSArray *previous = history.count > 1 ? [history subarrayWithRange:NSMakeRange(0, history.count - 1)] : @[];
    NSMutableDictionary *request = [@{@"account":self.account, @"peer":peer, @"message_id":e[@"message_id"], @"revision":@(revision), @"incoming":content, @"history":previous, @"profile":profile, @"examples":examples, @"model":cfg[@"model"], @"temperature":cfg[@"temperature"], @"group_enabled":cfg[@"groups"], @"group_without_at":cfg[@"group_without_at"]} mutableCopy];
    if (e[@"images"]) request[@"images"] = e[@"images"];
    GTLog(@"generation_started");
    NSString *account = self.account;
    [[GTClient shared] request:@"/v1/reply" body:request completion:^(NSDictionary *reply, NSString *error) {
        if (![self.account isEqual:account] || [self.revisions[scope] integerValue] != revision || ![self allowed:scope]) { GTLog(@"stale_response_discarded"); return; }
        if (error) { GTLog(error); return; }
        NSArray *segments = reply[@"segments"];
        if (![segments isKindOfClass:NSArray.class] || !segments.count || segments.count > 2 || ![reply[@"message_id"] isEqual:e[@"message_id"]] || [reply[@"revision"] integerValue] != revision) { GTLog(@"reply_identity_or_schema_invalid"); return; }
        for (id s in segments) if (![s isKindOfClass:NSString.class] || ![s length] || [s length] > 800) { GTLog(@"reply_schema_invalid"); return; }
        self.drafts[scope] = [@{@"segments":segments, @"revision":@(revision), @"message_id":e[@"message_id"], @"incoming":content, @"original":[segments componentsJoinedByString:@"\n"], @"needs_review":@([reply[@"needs_review"] boolValue]), @"account":account} mutableCopy];
        GTLog(@"reply_ready");
        if ([cfg[@"automatic"] boolValue] && ![reply[@"needs_review"] boolValue]) {
            if (UIApplication.sharedApplication.applicationState == UIApplicationStateActive) [self review:peer host:GTTop()];
            else GTLog(@"review_waiting_for_foreground_no_hidden_confirmation");
        }
    }];
}
- (void)review:(NSString *)peer host:(UIViewController *)host {
    NSString *scope = [self scope:peer]; NSMutableDictionary *draft = self.drafts[scope];
    if (!draft || !host || host.presentedViewController) { GTLog(@"no_draft_or_presenter_busy"); return; }
    NSString *original = draft[@"original"];
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:[@"审核回复 · " stringByAppendingString:peer] message:[NSString stringWithFormat:@"来信：%@\n\n%@\n\n修改会停止倒计时；未适配版本不能实发。", draft[@"incoming"], original] preferredStyle:UIAlertControllerStyleAlert];
    __block BOOL editing = NO, consumed = NO;
    [alert addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:^(__unused UIAlertAction *a) { consumed = YES; }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"修改" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a) {
        consumed = YES; editing = YES;
        UIAlertController *editor = [UIAlertController alertControllerWithTitle:@"修改后确认" message:@"只学习你明确修改的文字；最多保存此对象6组样本。" preferredStyle:UIAlertControllerStyleAlert];
        [editor addTextFieldWithConfigurationHandler:^(UITextField *f) { f.text = original; }];
        [editor addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
        [editor addAction:[UIAlertAction actionWithTitle:@"确认发送" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *b) {
            NSString *changed = editor.textFields.firstObject.text;
            if (changed.length && changed.length <= 800) { draft[@"segments"] = @[changed]; draft[@"edited"] = @YES; [self dispatch:peer draft:draft]; }
        }]];
        [host presentViewController:editor animated:YES completion:nil];
    }]];
    [alert addAction:[UIAlertAction actionWithTitle:@"确认发送" style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a) { consumed = YES; [self dispatch:peer draft:draft]; }]];
    [host presentViewController:alert animated:YES completion:nil];
    if ([GTConfig.shared.values[@"automatic"] boolValue] && ![draft[@"needs_review"] boolValue]) {
        alert.title = @"5秒无操作确认（修改可停止）";
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            if (consumed || editing || !alert.presentingViewController || UIApplication.sharedApplication.applicationState != UIApplicationStateActive) return;
            consumed = YES; [alert dismissViewControllerAnimated:YES completion:^{ [self dispatch:peer draft:draft]; }];
        });
    }
}
- (void)dispatch:(NSString *)peer draft:(NSMutableDictionary *)draft {
    NSString *scope = [self scope:peer];
    if (![self.account isEqual:draft[@"account"]] || self.drafts[scope] != draft || ![self allowed:scope] || [self.revisions[scope] integerValue] != [draft[@"revision"] integerValue] || [self.paused containsObject:scope]) { GTLog(@"send_stale_or_disabled"); return; }
    if (!GTCanSend()) { GTLog(@"send_unavailable_8075_not_device_verified"); return; }
    // Explicit conservative protection, not a promise of avoiding account enforcement.
    NSMutableDictionary *cfg = GTConfig.shared.values;
    NSString *day = [[NSISO8601DateFormatter new] stringFromDate:NSDate.date]; day = [day substringToIndex:10];
    if (![cfg[@"send_day"] isEqual:day]) { cfg[@"send_day"] = day; cfg[@"send_count"] = @0; }
    NSTimeInterval last = [cfg[@"last_attempt"] doubleValue];
    if ([cfg[@"send_count"] integerValue] + [draft[@"segments"] count] > 50 || NSDate.date.timeIntervalSince1970 - last < 15) { GTLog(@"rate_or_daily_limit_reached"); return; }
    NSArray *segments = draft[@"segments"];
    // Both segments reserved before first side effect. No silent retry after an unknown result.
    NSString *key = GTHash([NSString stringWithFormat:@"%@:%@", scope, draft[@"message_id"]]);
    NSMutableDictionary *ledger = cfg[@"ledger"];
    if (ledger[key] || ledger.count >= 5000) { GTLog(@"duplicate_or_ledger_full"); return; }
    ledger[key] = @"reserved"; cfg[@"blocked"][scope] = @YES; cfg[@"last_attempt"] = @(NSDate.date.timeIntervalSince1970); cfg[@"send_count"] = @([cfg[@"send_count"] integerValue] + segments.count);
    if (![GTConfig.shared save]) { [self.paused addObject:scope]; GTLog(@"send_blocked_ledger_not_persisted"); return; }
    self.pending[scope] = @{@"text":segments[0], @"key":key};
    BOOL submitted = GTSubmit(self.account, peer, segments[0]);
    if (!submitted) { ledger[key] = @"unknown"; [self.paused addObject:scope]; [GTConfig.shared save]; GTLog(@"send_unknown_peer_paused"); return; }
    if ([draft[@"edited"] boolValue]) {
        NSMutableArray *examples = [GTConfig.shared profile:scope][@"examples"];
        [examples addObject:@{@"incoming":draft[@"incoming"], @"original":draft[@"original"], @"edited":[segments componentsJoinedByString:@"\n"]}];
        while (examples.count > 6) [examples removeObjectAtIndex:0]; [GTConfig.shared save];
    }
    // A second segment requires a local echo of the first; do not chain from a void method return.
    if (segments.count > 1) GTLog(@"second_segment_held_requires_verified_delivery_adapter");
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        if (self.pending[scope]) { ledger[key] = @"unknown"; [self.paused addObject:scope]; [GTConfig.shared save]; GTLog(@"receipt_missing_peer_paused"); }
    });
}
@end
