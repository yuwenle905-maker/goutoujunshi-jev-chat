#import <UIKit/UIKit.h>
#ifdef __cplusplus
extern "C" {
#endif
int AleRunHUD(void);
NSString *AleEventFailure(void);
UIImage *AleScreenImage(void);
BOOL AleHostWindow(UIWindow *window);
void AleProbeWindow(UIWindow *window, BOOL enabled, void (^completion)(BOOL, NSString *));
void AleChooseEventRoute(UIWindow *window, void (^completion)(BOOL, NSString *));
#ifdef __cplusplus
}
#endif
