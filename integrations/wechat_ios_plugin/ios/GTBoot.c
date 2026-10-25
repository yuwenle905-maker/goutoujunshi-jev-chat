// C-only startup breadcrumb: no Objective-C classes, swizzling, network or chat data.
#include "GTBoot.h"
#include <sys/stat.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <os/log.h>

static const char *GoutouBootDirectory(void) {
#ifdef GT_BOOT_TEST_ROOT
    return GT_BOOT_TEST_ROOT;
#else
    return getenv("HOME");
#endif
}
int GoutouWechatAI_BootPath(char *buffer, unsigned long capacity) {
    const char *home = GoutouBootDirectory();
    if (!home || !buffer || capacity < 128) return 0;
    int count = snprintf(buffer, capacity, "%s/Library/Logs/GoutouAI-boot.log", home);
    return count > 0 && (unsigned long)count < capacity;
}
void GoutouWechatAI_BootMark(const char *code) {
    if (!code || strlen(code) > 100 || strspn(code, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.") != strlen(code)) return;
    os_log_with_type(OS_LOG_DEFAULT, OS_LOG_TYPE_DEFAULT, "GoutouWechatAI boot %{public}s", code);
    char path[4096], line[180];
    if (!GoutouWechatAI_BootPath(path, sizeof(path))) return;
    // Library/Logs may not exist in a fresh sandbox. Never follow the log symlink.
    char directory[4096]; snprintf(directory, sizeof(directory), "%s/Library/Logs", GoutouBootDirectory());
    mkdir(directory, 0700);
    int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW, 0600);
    if (fd < 0) return;
    if (flock(fd, LOCK_EX | LOCK_NB) != 0) { close(fd); return; }
    struct stat info;
    if (fstat(fd, &info) == 0 && info.st_size > 32768) ftruncate(fd, 0);
    int size = snprintf(line, sizeof(line), "%lld %s\n", (long long)time(NULL), code);
    if (size > 0 && size < (int)sizeof(line)) { ssize_t result = write(fd, line, (size_t)size); (void)result; fsync(fd); }
    flock(fd, LOCK_UN); close(fd);
}
void GoutouWechatAI_ClearBootLog(void) {
    char path[4096];
    if (!GoutouWechatAI_BootPath(path, sizeof(path))) return;
    int fd = open(path, O_WRONLY | O_NOFOLLOW, 0600);
    if (fd >= 0) { ftruncate(fd, 0); close(fd); }
}
