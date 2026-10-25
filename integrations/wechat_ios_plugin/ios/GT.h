#import <UIKit/UIKit.h>
#import <Security/Security.h>
#import <objc/runtime.h>
#import <objc/message.h>
#include <math.h>
#include <string.h>
#include "GTBoot.h"

// This is a compatibility target, NOT proof of a tested private ABI.
#ifndef GT_VERIFIED_8075_SEND
#define GT_VERIFIED_8075_SEND 0
#endif

void GTLog(NSString *code);
NSString *GTSecret(NSString *name);
BOOL GTSaveSecret(NSString *name, NSString *value);
id GTCall(id object, NSString *selector, NSArray *args);
BOOL GTObjectMethod(Class cls, SEL sel, NSUInteger count, BOOL returnsVoid);
void GTInstallAdapter(void);
void GTEnableRuntimeHooks(void);
BOOL GTCanSend(void);
BOOL GTSubmit(NSString *account, NSString *peer, NSString *text);
void GTPresent(UIViewController *host);

@interface GTWXAIConfig : NSObject
@property NSMutableDictionary *values;
+ (instancetype)shared;
- (BOOL)save;
- (NSMutableDictionary *)profile:(NSString *)scope;
@end

@interface GTWXAIClient : NSObject <NSURLSessionTaskDelegate>
+ (instancetype)shared;
- (void)request:(NSString *)path body:(NSDictionary *)body completion:(void (^)(NSDictionary *, NSString *))done;
@end

@interface GTWXAICoordinator : NSObject
@property NSString *account;
@property NSString *currentPeer;
@property NSMutableDictionary *histories;
@property NSMutableDictionary *revisions;
@property NSMutableDictionary *drafts;
@property NSMutableDictionary *seen;
@property NSMutableDictionary *pending;
@property NSMutableSet *paused;
+ (instancetype)shared;
- (NSString *)scope:(NSString *)peer;
- (void)observe:(NSDictionary *)event;
- (void)review:(NSString *)peer host:(UIViewController *)host;
- (void)cancel:(NSString *)peer;
@end

@interface GTWXAIHomeController : UIViewController
@end
@interface GTWXAISettingsController : UITableViewController
@property NSString *scope;
@end
