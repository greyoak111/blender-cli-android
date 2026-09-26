#include <stdio.h>
#include <dlfcn.h>

typedef int (*clGetPlatformIDs_t)(unsigned, void*, unsigned*);
typedef int (*clGetDeviceIDs_t)(void*, unsigned long, unsigned, void*, unsigned*);
typedef int (*clGetPlatformInfo_t)(void*, unsigned, unsigned long, void*, unsigned long*);

int main(void) {
    const char *names[] = {"libOpenCL.so", "/vendor/lib64/libOpenCL.so", "libOpenCL.so.1"};
    void *h = NULL;
    for (int i = 0; i < 3; i++) {
        h = dlopen(names[i], RTLD_NOW);
        printf("dlopen(\"%s\") -> %s\n", names[i], h ? "成功" : dlerror());
        if (h) break;
    }
    if (!h) return 1;

    clGetPlatformIDs_t getPlat = (clGetPlatformIDs_t)dlsym(h, "clGetPlatformIDs");
    if (!getPlat) { printf("找不到 clGetPlatformIDs\n"); return 1; }
    unsigned np = 0;
    int rc = getPlat(0, NULL, &np);
    printf("clGetPlatformIDs -> rc=%d, 平台数=%u\n", rc, np);
    if (rc != 0 || np == 0) return 0;

    void *plats[8];
    getPlat(8, plats, &np);
    clGetPlatformInfo_t getInfo = (clGetPlatformInfo_t)dlsym(h, "clGetPlatformInfo");
    char buf[256];
    if (getInfo) {
        /* CL_PLATFORM_NAME=0x0902, CL_PLATFORM_VERSION=0x0901 */
        if (getInfo(plats[0], 0x0902, sizeof(buf), buf, NULL) == 0) printf("平台名称: %s\n", buf);
        if (getInfo(plats[0], 0x0901, sizeof(buf), buf, NULL) == 0) printf("OpenCL 版本: %s\n", buf);
    }
    clGetDeviceIDs_t getDev = (clGetDeviceIDs_t)dlsym(h, "clGetDeviceIDs");
    if (getDev) {
        unsigned nd = 0;
        int r2 = getDev(plats[0], 4 /*CL_DEVICE_TYPE_GPU*/, 8, NULL, &nd);
        printf("clGetDeviceIDs(GPU) -> rc=%d, 设备数=%u\n", r2, nd);
    }
    return 0;
}
