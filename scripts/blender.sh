#!/system/bin/sh
# ─────────────────────────────────────────────────────────────────────
#  Blender 无头 CLI 启动包装器 —— 在 Android 上原生运行
#
#    GPU 链路: Blender → EGL(Mesa surfaceless) → Zink → Vulkan
#                      → Turnip(补丁版) → /dev/kgsl-3d0 → Adreno GPU
#
#  用法:
#    blender.sh --version
#    blender.sh -b scene.blend -f 1              # 渲染（EEVEE 走 GPU）
#    blender.sh -b --python script.py            # 跑 Python 脚本
#
#  可通过环境变量覆盖路径:
#    GLIBC_PREFIX   glibc 运行时前缀（默认 $HOME/blender-env/glibc-prefix）
#    DEBROOT        Debian 用户空间根目录（默认 $HOME/blender-env/debroot）
#    ICD            Vulkan ICD 配置路径（默认用补丁版 Mesa 自带的那份）
# ─────────────────────────────────────────────────────────────────────

BASE="${BLENDER_ENV:-$HOME/blender-env}"
GLIBC_PREFIX="${GLIBC_PREFIX:-$BASE/glibc-prefix}"
DEBROOT="${DEBROOT:-$BASE/debroot}"
B="$DEBROOT"
A="$B/usr/lib/aarch64-linux-gnu"

# ── 库搜索路径 ──────────────────────────────────────────────────────
# ⚠️ 绝不能把 bionic 库放进这里！
#    Termux 前缀的 lib/ 是 bionic（符号版本 LIBC / LIBC_N）
#    只有 lib/glibc/lib 才是 glibc。
#    混用会报满屏 `version 'LIBC' not found`。
LIB="$A:$GLIBC_PREFIX/glibc/lib"

# Debian 的库不止放一个目录：/usr/lib、blas/、lapack/、pulseaudio/ …
# 自动收集所有含 .so 的子目录，避免一个个补
for d in $(find "$B/usr/lib" "$B/lib" -type d 2>/dev/null); do
  case "$d" in *python3*|*lib-dynload*|*aarch64-linux-gnu) continue ;; esac
  ls "$d"/*.so* >/dev/null 2>&1 && LIB="$LIB:$d"
done

# ── Blender 资源与 Python ───────────────────────────────────────────
# Debian 把资源拆到 /usr/share/blender，且 Python 用系统库。
# 注意 BLENDER_SYSTEM_PYTHON 要指向**安装根**，不是 lib 目录。
export BLENDER_SYSTEM_RESOURCES="$B/usr/share/blender"
export BLENDER_SYSTEM_PYTHON="$B/usr"

# ── GPU（四个条件缺一不可）────────────────────────────────────────
# 1) libglvnd 必须能找到 Mesa 的 EGL 厂商驱动。
#    缺了它只会看到误导性的 `EGL_BAD_PARAMETER` —— 这是最难的一个坎。
export __EGL_VENDOR_LIBRARY_FILENAMES="$B/usr/share/glvnd/egl_vendor.d/50_mesa.json"

# 2) 安卓没有 /dev/dri/*，只能用 surfaceless 平台（GBM / X11 均不可用）
export EGL_PLATFORM=surfaceless

# 3) OpenGL → Vulkan 转译
export GALLIUM_DRIVER=zink
export MESA_LOADER_DRIVER_OVERRIDE=zink

# 4) Turnip 走 KGSL（不依赖被 SELinux 挡住的 DRM 节点）
#    补丁包自带的 ICD 里写的是绝对路径 /usr/lib/...，在非标准根目录下无效，
#    这里自动生成一份路径修正过的。
ICD_SRC="${ICD:-$B/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json}"
ICD_FIXED="$BASE/patched_icd.json"
if [ -f "$ICD_SRC" ] && [ ! -f "$ICD_FIXED" ]; then
  mkdir -p "$BASE"
  # 只替换路径开头的 "/usr/ → "$B/usr/，
  # 不能替换中间的 /usr/lib/ ，否则 aarch64-linux-gnu 会被重复拼接
  sed "s|\"/usr/|\"$B/usr/|g" "$ICD_SRC" > "$ICD_FIXED" 2>/dev/null
fi
export VK_ICD_FILENAMES="${ICD_FIXED:-$ICD_SRC}"

exec "$GLIBC_PREFIX/glibc/lib/ld-linux-aarch64.so.1" \
  --library-path "$LIB" "$B/usr/bin/blender" "$@"
