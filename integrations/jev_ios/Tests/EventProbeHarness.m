#import <UIKit/UIKit.h>
#import "Bridge.h"
#import "HUDMainApplication.h"
#import "TouchBurstProbe.h"

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
    // Exercise the production UIKit-source gate and sink binding as well as AX
    // delivery. A normal UIApplicationMain launch is not global HUD hosting.
    BOOL nativeReady = [(HUDMainApplication *)app prepareAleEvents];
    self.window = [[ProbeWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UIViewController *root = [UIViewController new];
    root.view.backgroundColor = UIColor.systemBackgroundColor;
    self.window.rootViewController = root; self.window.hidden = NO;
    UILabel *label = [[UILabel alloc] initWithFrame:CGRectMake(30, 180, 330, 220)];
    label.numberOfLines = 0; label.text = @"Testing the production event source…";
    [root.view addSubview:label];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        AleProbeWindow(self.window, NO, ^(BOOL disabledPassed, NSString *disabledDetail) {
            AleProbeWindow(self.window, YES, ^(BOOL enabledPassed, NSString *enabledDetail) {
              AleProbeTouchBurst(self.window, ^(BOOL burstPassed, NSDictionary *burst) {
                BOOL passed = nativeReady && !disabledPassed && enabledPassed && burstPassed;
                NSDictionary *result = @{@"passed":@(passed), @"disabled_target_rejected":@(!disabledPassed),
                    @"burst_routing":burst,
                    @"native_sources_verified_before_sink":@(nativeReady),
                    @"native_source_stage":[(HUDMainApplication *)app aleEventStage] ?: @"",
                    @"enabled_target_received_action":@(enabledPassed), @"negative_detail":disabledDetail ?: @"",
                    @"positive_detail":enabledDetail ?: @"", @"ios":UIDevice.currentDevice.systemVersion,
                    @"window_became_key":@(self.window.isKeyWindow), @"global_hosting_tested":@NO};
                NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
                NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
                [data writeToURL:[documents URLByAppendingPathComponent:@"event-probe.json"] atomically:YES];
                label.text = passed ? @"PASS\nNative source ready\nRapid taps: 3 actions\nReal UIPan moved view\nOutside touches rejected" : [NSString stringWithFormat:@"FAIL\n%@\n%@", enabledDetail, burst];
              });
            });
        });
    });
    return YES;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, NSStringFromClass(HUDMainApplication.class), NSStringFromClass(ProbeApp.class)); }
}
