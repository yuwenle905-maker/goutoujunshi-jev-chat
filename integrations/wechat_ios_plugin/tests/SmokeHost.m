// Synthetic UIKit host only. This does NOT reproduce private WeChat internals.
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
static int received=0;
@interface CMessageMgr : NSObject
- (void)AsyncOnAddMsg:(id)peer MsgWrap:(id)wrap;
@end
@implementation CMessageMgr
- (void)AsyncOnAddMsg:(id)peer MsgWrap:(id)wrap { received++; }
@end
@interface NewSettingViewController : UIViewController
@end
@implementation NewSettingViewController
- (void)viewDidLoad { [super viewDidLoad]; self.view.backgroundColor=UIColor.systemBackgroundColor; }
@end
@interface GoutouSmokeHostDelegate : UIResponder <UIApplicationDelegate>
@property UIWindow *window;
@end
@implementation GoutouSmokeHostDelegate
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController=[[UINavigationController alloc] initWithRootViewController:[NewSettingViewController new]];
    [self.window makeKeyAndVisible];
    IMP original=class_getMethodImplementation(CMessageMgr.class,@selector(AsyncOnAddMsg:MsgWrap:));
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,6*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        NSMutableDictionary *result=[NSMutableDictionary new];
        result[@"startup_survived"]=@YES;
        result[@"private_hook_absent_until_opt_in"]=@(class_getMethodImplementation(CMessageMgr.class,@selector(AsyncOnAddMsg:MsgWrap:))==original);
        NSUInteger gestures=0;for(UIGestureRecognizer *g in self.window.gestureRecognizers) if([g isKindOfClass:UILongPressGestureRecognizer.class]&&((UILongPressGestureRecognizer *)g).numberOfTouchesRequired==3)gestures++;
        result[@"public_shortcut_count"]=@(gestures);
        Class settingsClass=NSClassFromString(@"GTWXAISettingsController");
        result[@"namespaced_settings_class_present"]=@(settingsClass!=Nil);
        @try {
            UITableViewController *settings=[settingsClass new];
            UISwitch *toggle=[UISwitch new];toggle.tag=0;toggle.on=YES;
            [settings performSelector:NSSelectorFromString(@"toggle:") withObject:toggle];
            IMP installed=class_getMethodImplementation(CMessageMgr.class,@selector(AsyncOnAddMsg:MsgWrap:));
            result[@"private_hook_installed_after_opt_in"]=@(installed!=original);
            [settings performSelector:NSSelectorFromString(@"toggle:") withObject:toggle];
            result[@"repeat_enable_does_not_rehook"]=@(class_getMethodImplementation(CMessageMgr.class,@selector(AsyncOnAddMsg:MsgWrap:))==installed);
            CMessageMgr *manager=[CMessageMgr new];[manager AsyncOnAddMsg:@"synthetic" MsgWrap:nil];
            result[@"original_receive_called_once"]=@(received==1);
            toggle.on=NO;[settings performSelector:NSSelectorFromString(@"toggle:") withObject:toggle];
            UIViewController *home=[NSClassFromString(@"GTWXAIHomeController") new];[home loadViewIfNeeded];
            result[@"settings_ui_constructed"]=@(home.view!=nil);
        } @catch(__unused NSException *e) {result[@"exception"]=@YES;}
        NSData *data=[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
        NSString *path=[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/goutou-smoke-result.json"];
        [data writeToFile:path options:NSDataWritingAtomic error:nil];
    });
    return YES;
}
@end
int main(int argc,char **argv) { @autoreleasepool {return UIApplicationMain(argc,argv,nil,NSStringFromClass(GoutouSmokeHostDelegate.class));} }
