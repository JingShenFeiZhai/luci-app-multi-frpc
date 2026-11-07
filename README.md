# LUCI-APP-MULTI-FRPC

一款 OpenWrt / LuCI 的 frpc 客户端插件，支持同时连接多台 frps 服务器。

本项目 fork 自 [justice2001/luci-app-multi-frpc](https://github.com/justice2001/luci-app-multi-frpc)：在其 1.0.1 基础上修复了安装冲突、LuCI 崩溃等问题，并新增按服务器分配服务等能力。上游基于 [luci-app-frpc](https://github.com/coolsnowwolf/luci/tree/master/applications/luci-app-frpc) 修改。

## 特性

- 一条 frpc 同时连接多台 frps，每台服务器独立进程、独立客户端日志
- 服务可指定只发布到部分服务器（v1.0.3+）
- 与固件自带的 `luci-app-frpc` 使用独立命名空间，可同时安装
- 支持 HTTP / HTTPS / TCP / UDP / STCP / XTCP 及常用 plugin

## 命名空间

| 项目 | luci-app-frpc | luci-app-multi-frpc |
| --- | --- | --- |
| 配置 | `/etc/config/frp` | `/etc/config/multi-frpc` |
| 启动脚本 | `/etc/init.d/frp` | `/etc/init.d/multi-frpc` |
| 菜单 | 服务 → Frp | 服务 → Multi Frpc |
| 运行目录 | `/var/etc/frp` | `/var/etc/multi-frpc` |

首次安装时若检测到 `/etc/config/frp`，会自动迁移到 `/etc/config/multi-frpc` 并保持总开关关闭。确认新插件正常后，可卸载 `luci-app-frpc`、`luci-i18n-frpc-zh-cn`。

## 安装

iStore「手动安装」依次上传主包和可选语言包；或：

```sh
opkg install luci-app-multi-frpc_<版本>_all.ipk
opkg install luci-i18n-multi-frpc-zh-cn_<版本>_all.ipk   # 可选
```

升级时提示 `resolve_conffiles ... /etc/config/multi-frpc-opkg` 属正常（保留现有配置），删除该 `-opkg` 文件即可。安装完成后刷新 LuCI。

## 使用

1. 「服务器列表」添加 frps：备注名、地址、`bind_port`、token，勾选启用。
2. 「服务列表」添加要转发的服务：备注名（唯一）、协议类型、本地地址/端口；TCP/UDP 填远程端口，HTTP/HTTPS 填域名，STCP/XTCP 填角色与密钥。
3. 需要时在服务里勾选「目标服务器」，只发布到指定 frps；不勾选表示所有已启用服务器。
4. 「基本设置」勾选启用，点「保存并应用」。

visitor 需要不同本地监听地址时，为每台服务器各建一条服务，分别设置本地地址/端口并只勾选对应服务器。

## 构建

```sh
# OpenWrt SDK / 源码树
make package/luci-app-multi-frpc/compile V=s

# 无 SDK，直接生成 ipk（输出到 dist/）
python3 tools/build-ipk.py
```

## 说明

- 日志：`/var/etc/multi-frpc/frp.log`（插件），`/var/etc/multi-frpc/frpc-<服务器名>.log`（客户端）。
- `tcp_mux` 必须与 frps 一致，否则登录失败。
- 从 1.0.1 升级前请备份 `/etc/config/frp`（旧版本未将其标记为 conffiles）。
- 服务备注名会作为 frpc 配置的段名，必须唯一；删除或重建服务器后请重新确认「目标服务器」。

## 鸣谢

- [justice2001/luci-app-multi-frpc](https://github.com/justice2001/luci-app-multi-frpc)：本项目的上游
- [luci-app-frpc](https://github.com/coolsnowwolf/luci/tree/master/applications/luci-app-frpc)：最初的 LuCI 实现
- [luci-app-adguardhome](https://github.com/rufengsuixing/luci-app-adguardhome)：部分代码参考
