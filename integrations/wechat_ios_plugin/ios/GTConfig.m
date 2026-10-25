#import "GT.h"

static NSMutableArray *GTLogs;
void GTLog(NSString *code) {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!GTLogs) GTLogs = [NSMutableArray new];
        [GTLogs addObject:[NSString stringWithFormat:@"%@ %@", NSDate.date, code]];
        if (GTLogs.count > 200) [GTLogs removeObjectAtIndex:0];
        [[NSNotificationCenter defaultCenter] postNotificationName:@"GTChanged" object:nil];
    });
}
NSString *GTLogText(void) { return [GTLogs componentsJoinedByString:@"\n"] ?: @"暂无日志"; }
void GTClearLogs(void) { [GTLogs removeAllObjects]; GTLog(@"logs_cleared"); }

static NSMutableDictionary *GTKeyQuery(NSString *name) {
    return [@{(__bridge id)kSecClass:(__bridge id)kSecClassGenericPassword,
              (__bridge id)kSecAttrService:[NSBundle.mainBundle.bundleIdentifier stringByAppendingString:@".GoutouAI"],
              (__bridge id)kSecAttrAccount:name} mutableCopy];
}
NSString *GTSecret(NSString *name) {
    NSMutableDictionary *q = GTKeyQuery(name);
    q[(__bridge id)kSecReturnData] = @YES;
    CFTypeRef result = NULL;
    if (SecItemCopyMatching((__bridge CFDictionaryRef)q, &result) != errSecSuccess) return @"";
    NSData *data = CFBridgingRelease(result);
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"";
}
BOOL GTSaveSecret(NSString *name, NSString *value) {
    NSMutableDictionary *q = GTKeyQuery(name);
    if (!value.length) { OSStatus s = SecItemDelete((__bridge CFDictionaryRef)q); return s == errSecSuccess || s == errSecItemNotFound; }
    NSDictionary *attrs = @{(__bridge id)kSecValueData:[value dataUsingEncoding:NSUTF8StringEncoding],
                            (__bridge id)kSecAttrAccessible:(__bridge id)kSecAttrAccessibleWhenUnlockedThisDeviceOnly};
    OSStatus status = SecItemUpdate((__bridge CFDictionaryRef)q, (__bridge CFDictionaryRef)attrs);
    if (status == errSecItemNotFound) { [q addEntriesFromDictionary:attrs]; status = SecItemAdd((__bridge CFDictionaryRef)q, NULL); }
    return status == errSecSuccess;
}
static NSURL *GTConfigURL(void) {
    NSURL *dir = [[NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:@"GoutouAI" isDirectory:YES];
    [NSFileManager.defaultManager createDirectoryAtURL:dir withIntermediateDirectories:YES attributes:@{NSFileProtectionKey:NSFileProtectionComplete} error:nil];
    [dir setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil];
    return [dir URLByAppendingPathComponent:@"config.json"];
}
@implementation GTConfig
+ (instancetype)shared { static GTConfig *v; static dispatch_once_t once; dispatch_once(&once, ^{ v = [GTConfig new]; }); return v; }
- (instancetype)init {
    if ((self = [super init])) {
        NSData *data = [NSData dataWithContentsOfURL:GTConfigURL()];
        id decoded = data ? [NSJSONSerialization JSONObjectWithData:data options:NSJSONReadingMutableContainers error:nil] : nil;
        _values = [@{@"enabled":@NO, @"automatic":@NO, @"all_friends":@NO,
                     @"groups":@NO, @"group_without_at":@NO, @"cloud_consent":@NO,
                     @"endpoint":@"", @"model":@"deepseek-flash", @"temperature":@0.9,
                     @"persona":@"短句、直接、自然；按我的真实改稿学习，不强加网梗。",
                     @"meme_bank":@"有点东西；这波确实…；主打一个…；绷不住了（按场景少量使用，不嘲讽对方）",
                     @"prefix":@"", @"suffix":@"", @"profiles":[NSMutableDictionary new], @"ledger":[NSMutableDictionary new], @"blocked":[NSMutableDictionary new]} mutableCopy];
        if ([decoded isKindOfClass:NSDictionary.class]) [_values addEntriesFromDictionary:decoded];
        if (![_values[@"profiles"] isKindOfClass:NSMutableDictionary.class]) _values[@"profiles"] = [NSMutableDictionary new];
        if (![_values[@"ledger"] isKindOfClass:NSMutableDictionary.class]) _values[@"ledger"] = [NSMutableDictionary new];
    } return self;
}
- (NSMutableDictionary *)profile:(NSString *)scope {
    NSMutableDictionary *p = self.values[@"profiles"][scope];
    if (!p) { p = [@{@"enabled":@NO, @"persona":@"", @"stage":@"", @"goal":@"", @"state":@"", @"boundaries":@"", @"examples":[NSMutableArray new]} mutableCopy]; self.values[@"profiles"][scope] = p; }
    return p;
}
- (BOOL)save {
    NSError *err;
    NSData *data = [NSJSONSerialization dataWithJSONObject:self.values options:0 error:&err];
    if (!data || ![data writeToURL:GTConfigURL() options:NSDataWritingAtomic | NSDataWritingFileProtectionComplete error:&err]) { GTLog(@"config_write_failed"); return NO; }
    return YES;
}
@end

@implementation GTClient
+ (instancetype)shared { static GTClient *v; static dispatch_once_t once; dispatch_once(&once, ^{v = [GTClient new];}); return v; }
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task willPerformHTTPRedirection:(NSHTTPURLResponse *)response newRequest:(NSURLRequest *)request completionHandler:(void (^)(NSURLRequest *))completionHandler { completionHandler(nil); }
- (void)request:(NSString *)path body:(NSDictionary *)body completion:(void (^)(NSDictionary *, NSString *))done {
    NSString *base = GTConfig.shared.values[@"endpoint"];
    NSURLComponents *c = [NSURLComponents componentsWithString:base];
    if (![c.scheme.lowercaseString isEqual:@"https"] || !c.host.length || c.user || c.password || c.query || c.fragment || (c.path.length && ![c.path isEqual:@"/"])) { done(nil, @"endpoint_requires_https_origin"); return; }
    c.path = path;
    NSString *token = GTSecret(@"device_token");
    if (!token.length) { done(nil, @"device_token_missing_or_device_locked"); return; }
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:c.URL];
    req.timeoutInterval = 55;
    req.HTTPMethod = body ? @"POST" : @"GET";
    [req setValue:[@"Bearer " stringByAppendingString:token] forHTTPHeaderField:@"Authorization"];
    NSString *key = GTSecret(@"deepseek_key");
    if (key.length) [req setValue:key forHTTPHeaderField:@"X-DeepSeek-Key"];
    if (body) { req.HTTPBody = [NSJSONSerialization dataWithJSONObject:body options:0 error:nil]; [req setValue:@"application/json" forHTTPHeaderField:@"Content-Type"]; }
    NSURLSessionConfiguration *cfg = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    cfg.HTTPCookieStorage = nil; cfg.URLCache = nil;
    NSURLSession *session = [NSURLSession sessionWithConfiguration:cfg delegate:self delegateQueue:nil];
    [[session dataTaskWithRequest:req completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        NSDictionary *json = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        NSInteger status = [(NSHTTPURLResponse *)response statusCode];
        NSString *failure = error ? @"network_error" : (status != 200 ? [NSString stringWithFormat:@"backend_http_%ld", (long)status] : (![json isKindOfClass:NSDictionary.class] ? @"invalid_response" : nil));
        [session finishTasksAndInvalidate];
        dispatch_async(dispatch_get_main_queue(), ^{ done(failure ? nil : json, failure); });
    }] resume];
}
@end
