//
//  HUDMainApplication.h
//  TrollSpeed
//
//  Created by Lessica on 2024/1/24.
//

#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface HUDMainApplication : UIApplication
@property (nonatomic, readonly) BOOL aleEventsReady;
@property (nonatomic, readonly) NSString *aleEventStage;
- (BOOL)prepareAleEvents;
@end

NS_ASSUME_NONNULL_END
