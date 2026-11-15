#import <UIKit/UIKit.h>
#import "Bridge.h"

@interface ProbeWindow : UIWindow
@end
@implementation ProbeWindow
- (BOOL)canBecomeKeyWindow { return NO; }
@end

@interface ProbeApp : UIResponder <UIApplicationDelegate>
@property (nonatomic, strong) UIWindow *window;
@end
@implementation ProbeApp
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window = [[ProbeWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UIViewController *root = [UIViewController new];
    root.view.backgroundColor = UIColor.systemBackgroundColor;
    self.window.rootViewController = root; self.window.hidden = NO;
    UILabel *label = [[UILabel alloc] initWithFrame:CGRectMake(30, 180, 330, 220)];
    label.numberOfLines = 0; label.text = @"Testing the production event source…";
    [root.view addSubview:label];
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
    return YES;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(ProbeApp.class)); }
}
