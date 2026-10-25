#include "GTBoot.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
int main(void) {
    char path[4096],contents[512];
    assert(GoutouWechatAI_BootPath(path,sizeof(path)));
    GoutouWechatAI_ClearBootLog();
    GoutouWechatAI_BootMark("test_boot_started");
    GoutouWechatAI_BootMark("must not log a body or credential!");
    FILE *f=fopen(path,"rb"); assert(f); size_t n=fread(contents,1,sizeof(contents)-1,f); contents[n]=0; fclose(f);
    assert(strstr(contents,"test_boot_started")); assert(!strstr(contents,"credential"));
    struct stat info; assert(!stat(path,&info)); assert((info.st_mode&0777)==0600);
    f=fopen(path,"wb"); assert(f); for(int i=0;i<40000;i++)fputc('x',f); fclose(f);
    GoutouWechatAI_BootMark("rotation_verified"); assert(!stat(path,&info)); assert(info.st_size<200);
    GoutouWechatAI_ClearBootLog(); assert(!stat(path,&info)); assert(info.st_size==0);
    puts("boot log: persistence, redaction, permissions, bounds and clear passed");
    return 0;
}
