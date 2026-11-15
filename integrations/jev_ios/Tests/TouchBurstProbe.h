#import <UIKit/UIKit.h>
#ifdef __cplusplus
extern "C" {
#endif
void AleProbeTouchBurst(UIWindow *window, void (^completion)(BOOL, NSDictionary *));
void AleProbeProgress(NSString *stage);
#ifdef __cplusplus
}
#endif
