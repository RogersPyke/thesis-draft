# curobo

安装curobo的时候一定使用：

--no-build-isolation --no-cache-dir --no-deps

否则会触发pip的行为导致以下错误链条：

当你不带 --no-deps 运行 pip install 时，pip 扫描 curobo 的 requirements.txt。-> pip 发现 torch 有更高版本（比如针对 CUDA 13 编译的预览版或最新稳定版），于是为了“满足依赖”，它背着你偷偷把本地稳健的 torch 2.x (CUDA 12.1) 升级了。-> 由于没有 --no-build-isolation，pip 在一个纯净的临时环境里编译 curobo。这个环境里只有刚刚拉下来的“最新版” torch. -> curobo 的源码在编译时，通过 torch.utils.cpp_extension 获取编译参数。既然 torch 是 13.0 版本的，它就会告诉编译器：“请链接到 libcudart.so.13。” -> 编译出来的 .whl 被安装回你的主环境。但你的物理机（BAAI 集群节点）上只装了 CUDA 12.1 的驱动和 Toolkit。-> 当 Python 执行 import curobo 时，动态链接器（ld.so）尝试加载扩展库，发现系统里根本没有 libcudart.so.13，于是抛出错误，导致整个 CuroboPlanner 类定义直接从内存中“蒸发”。

因此必须使用手动安装方式过滤curobo的一系列依赖。三个参数缺一不可，否则（1）隔离环境找不到torch（2）使用缓存编译（3）自动更新依赖导致一切爆炸。

# Pytorch3d

安装的时候会出现：缺少编译器。

conda install -y gxx_linux-64 gcc_linux-64

pip install "git+https://github.com/facebookresearch/pytorch3d.git@stable" --no-build-isolation --no-deps --no-cache-dir

如果用的12.1会因为太新无法安装，所以需要降级：

conda install gcc=11.4 gxx=11.4

# 额外环境

由于自定义脚本需要配置文件，需要安装Pyyaml。

由于要进行打包，需要安装conda-pack。