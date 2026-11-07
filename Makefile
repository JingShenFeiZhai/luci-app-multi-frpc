#
# Copyright (C) 2008-2014 The LuCI Team <luci@lists.subsignal.org>
#
# This is free software, licensed under the Apache License, Version 2.0 .
#

include $(TOPDIR)/rules.mk

LUCI_TITLE:=LuCI support for FRPC (multiple frps servers)
LUCI_DEPENDS:=+wget +frpc
LUCI_PKGARCH:=all

PKG_NAME:=luci-app-multi-frpc
PKG_VERSION:=1.0.3
PKG_RELEASE:=1
PKG_LICENSE:=Apache-2.0

define Package/$(PKG_NAME)/conffiles
/etc/config/multi-frpc
endef

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
