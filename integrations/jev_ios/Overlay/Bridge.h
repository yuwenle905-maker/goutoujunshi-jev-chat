#import <UIKit/UIKit.h>
#ifdef __cplusplus
extern "C" {
#endif
int AleRunHUD(void);
NSString *AleEventFailure(void);
UIImage *AleScreenImage(void);
BOOL AleHostWindow(UIWindow *window);
BOOL AleRouteTouch(UIWindow *window, CGPoint point, NSInteger pointer, UITouchPhase phase);
NSUInteger AleAcceptedTouchFrames(void);
NSString *AleHardwareInputStatus(void);
void AleProbeWindow(UIWindow *window, BOOL enabled, void (^completion)(BOOL, NSString *));
#ifdef __cplusplus
}
#endif
