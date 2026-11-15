#import <UIKit/UIKit.h>
#import "Bridge.h"
#import "TSEventFetcher.h"

@interface ProbeWindow : UIWindow
@end
@implementation ProbeWindow
- (BOOL)canBecomeKeyWindow { return NO; }
@end

@interface ProbeScene : UIResponder <UIWindowSceneDelegate>
@property (nonatomic, strong) UIWindow *window;
@end
@implementation ProbeScene
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.window = [[ProbeWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    UIViewController *root = [UIViewController new];
    root.view.backgroundColor = UIColor.systemBackgroundColor;
    self.window.rootViewController = root; self.window.hidden = NO;
    UILabel *label = [[UILabel alloc] initWithFrame:CGRectMake(30, 180, 330, 220)];
    label.numberOfLines = 0; label.text = @"Testing the production event source…";
    [root.view addSubview:label];
    (void)[TSEventFetcher deliveryCount];
    NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        for (int i = 0; i < 60; i++) {
            NSDictionary *progress = @{@"stage":[TSEventFetcher deliveryStage]};
            NSData *data = [NSJSONSerialization dataWithJSONObject:progress options:0 error:nil];
            [data writeToURL:[documents URLByAppendingPathComponent:@"event-progress.json"] atomically:YES];
            [NSThread sleepForTimeInterval:0.5];
        }
    });
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        AleChooseEventRoute(self.window, ^(BOOL passed, NSString *detail) {
                NSDictionary *result = @{@"passed":@(passed), @"route_details":detail ?: @"", @"ios":UIDevice.currentDevice.systemVersion,
                    @"window_became_key":@(self.window.isKeyWindow), @"global_hosting_tested":@NO};
                NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
                NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
                [data writeToURL:[documents URLByAppendingPathComponent:@"event-probe.json"] atomically:YES];
                label.text = passed ? @"PASS\nDisabled button: 0 actions\nEnabled button: 1 action\nWindow remains non-key" : [@"FAIL\n" stringByAppendingString:detail ?: @""];
        });
    });
}
@end
@interface ProbeApp : UIResponder <UIApplicationDelegate>
@end
@implementation ProbeApp
- (UISceneConfiguration *)application:(UIApplication *)app configurationForConnectingSceneSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    UISceneConfiguration *config = [[UISceneConfiguration alloc] initWithName:@"Probe" sessionRole:session.role];
    config.delegateClass = ProbeScene.class; return config;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(ProbeApp.class)); }
}
