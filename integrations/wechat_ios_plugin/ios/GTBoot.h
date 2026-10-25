#ifndef GOUTOU_WECHAT_AI_BOOT_H
#define GOUTOU_WECHAT_AI_BOOT_H
#ifdef __cplusplus
extern "C" {
#endif
void GoutouWechatAI_BootMark(const char *code);
int GoutouWechatAI_BootPath(char *buffer, unsigned long capacity);
void GoutouWechatAI_ClearBootLog(void);
#ifdef __cplusplus
}
#endif
#endif
