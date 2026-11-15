//
//  IOHIDEvent+KIF.h
//  KIF
//
//  Created by Thomas Bonnin on 7/6/15.
//

#import <Foundation/Foundation.h>
#import "IOKit+SPI.h"

typedef struct __IOHIDEvent * IOHIDEventRef;
#ifdef __cplusplus
extern "C" {
#endif
IOHIDEventRef kif_IOHIDEventWithTouches(NSArray *touches) CF_RETURNS_RETAINED;
#ifdef __cplusplus
}
#endif
